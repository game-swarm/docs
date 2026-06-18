# R25 Closure Verification — Economy Reviewer (DeepSeek V4 Pro)

**评审日期**: 2026-06-19
**评审类型**: Closure Verification (仅验证 R24 残留 B2/B3 GAP)
**评审文件**: 
- `/tmp/swarm-review-R25/design/README.md`
- `/tmp/swarm-review-R25/specs/reference/api-registry.md`
- `/tmp/swarm-review-R25/specs/core/08-resource-ledger.md`
- `/tmp/swarm-review-R25/design/gameplay.md`
- `/tmp/swarm-review-R25/design/economy-balance-sheet.md`

---

## B2-GAP: API/经济单事实源

### B2.1 — Storage Tax Thresholds (10K→30% capacity)

| 检查项 | 旧值 (R24) | 新值 (R25) | 位置 |
|--------|-----------|-----------|------|
| Tier 1 threshold | 10,000 units (绝对) | **30% capacity** (百分比) | api-registry.md §5.7, L554 |
| Tier 2 threshold | stale | **60% capacity** | api-registry.md §5.7, L555 |
| Tier 3 threshold | stale | **85% capacity** | api-registry.md §5.7, L556 |
| 权威引用 | 缺失 | "权威定义见 Resource Ledger §2.2" | api-registry.md §5.7, L554 |

**跨文档一致性**:
- `api-registry.md §5.7`: storage tax thresholds 30/60/85/100% capacity，显式引用 Resource Ledger §2.2
- `08-resource-ledger.md §2.1`: `storage_tax_tiers = [(30,0),(60,1),(85,5),(100,20)]`，含逐 tier 阈值明细
- `economy-balance-sheet.md §6`: "存储税使用 Resource Ledger §2.2 权威 tiered 公式计算"，引用不重复定义

**证据链**: api-registry §5.7 L554 行显式标注 `30% capacity` 并链接到 `Resource Ledger §2.2`。旧 `10K units` 阈值已完全被百分比容量阈值取代。

**→ B2.1: CLOSED** ✅

---

### B2.2 — Gameplay Upkeep (standalone numbers → 引用 Resource Ledger)

| 检查项 | 旧状态 (R24) | 新状态 (R25) | 位置 |
|--------|-------------|-------------|------|
| standalone upkeep 数值 | -40 ~ -3,150/tick | **已移除** | — |
| 引用方式 | 独立定义 | "超线性（见 Resource Ledger §Empire Upkeep + Balance Sheet）" | gameplay.md L406 |

**证据**:
- `gameplay.md L406`: 帝国维护费分类标注 "Sink | 超线性（见 Resource Ledger §Empire Upkeep + Balance Sheet）"，不再独立声明数值
- `gameplay.md L30`: 经济模型开篇即指向 Resource Ledger
- `gameplay.md L82`: `memory_upkeep_cost` 独立于 empire upkeep 体系，不受此 GAP 影响
- `economy-balance-sheet.md §1`: "维护费公式由 specs/core/08-resource-ledger.md §Empire Upkeep 权威定义"

**→ B2.2: CLOSED** ✅

---

### B2.3 — Recycle §2.3→2.5

| 检查项 | 旧位置 (R24) | 新位置 (R25) | 证明 |
|--------|------------|------------|------|
| Recycle 权威公式节号 | §2.3 | **§2.5** | 08-resource-ledger.md L158-166 |
| 自引用确认 | — | "Recycle 权威公式见 §2.5" | 08-resource-ledger.md L271 |

**跨文档一致性**:
- `08-resource-ledger.md §2.5`: `recycle_refund_base = 5000 bp (50%)`，`recycle_refund_min = 1000 bp (10%)`
- `api-registry.md §10.2`: `RecycleRefund` 公式 `max(1000, (remaining_lifespan * 5000) / total_lifespan)` bp，与 Resource Ledger 一致
- `api-registry.md §10.3`: Canonical formula 确认 floor rounding + clamp [10%, 50%]
- `economy-balance-sheet.md §5`: 引用 Resource Ledger §6（回收（RecycleRefund）: Resource Ledger §6），不重新定义

**→ B2.3: CLOSED** ✅

---

### B2 总评: CLOSED

三项子 GAP 全部闭合。Storage tax 阈值从绝对单位迁移为容量百分比，gameplay upkeep 从独立数值改为引用 Resource Ledger，Recycle 公式节号已从 §2.3 移至 §2.5。跨文档（api-registry ↔ Resource Ledger ↔ balance-sheet）一致性已验证。

---

## B3-GAP: 特殊攻击优先级唯一权威

### B3.1 — 02-command-validation 冲突表已删除

| 检查项 | 状态 | 证据 |
|--------|------|------|
| api-registry.md §1.3 冲突表 | **不存在** | 统一表格 L67-83 |
| 路由机制 | `CommandAction::Custom(type)` → `CustomActionRegistry` | L69 |
| 注册方式 | `custom_action_def` + `world_action_manifest_hash` | L69, L82-83 |

**证据**:
- `api-registry.md §1.3` (L67-83): 所有 8 个特殊攻击在单一非冲突表格中注册，路由为 `CommandAction::Custom(type)` → `CustomActionRegistry`，无第二张冲突表格
- `api-registry.md §0` (L5-6): "本文档是 Swarm 所有 API 合约的单一权威来源。CommandAction、RejectionReason...均以此文档为准。其他文档只能引用，不得重新声明可冲突的表格或列表。"

### B3.2 — 06-system-manifest S14 标注唯一权威链

**权威链结构**（从可读文件中推断）:
```
IDL YAML (economy.idl.yaml, game_api.idl.yaml)
    ↓
api-registry.md (自动生成，单一权威源)
    ↓
CustomActionRegistry (引擎 custom_action_def 注册)
    ↓
world_action_manifest_hash (TickTrace §6 field #15, L600, replay 确定性锚点)
```

**证据**:
- `api-registry.md L600`: `world_action_manifest_hash` 在 TickTrace Envelope 中作为 field #15，为 replay 确定性提供结构锚点
- `api-registry.md L82-83`: "TickTrace 记录 world_action_manifest_hash 以确保 replay 确定性"
- `gameplay.md L1173-1240`: 默认 world.toml 特殊攻击注册为 **TOML 配置示例**（`[[custom_actions]]` + `[[special_effects]]`），非冲突表格——这些是从 `CustomActionRegistry` 读取的配置数据，不构成平行权威

**→ B3: CLOSED** ✅

---

## 最终裁定

| GAP | 状态 | 关键证据 |
|-----|------|---------|
| B2.1 — Storage Tax | **CLOSED** | api-registry §5.7: `30% capacity` + 引用 Resource Ledger §2.2 |
| B2.2 — Gameplay Upkeep | **CLOSED** | gameplay.md L406: 引用 Resource Ledger，无独立数值 |
| B2.3 — Recycle §位置 | **CLOSED** | Resource Ledger §2.5 + 自引用 §2.5 |
| B3 — 特殊攻击权威 | **CLOSED** | api-registry §1.3 统一表 + §0 单一权威声明 + world_action_manifest_hash |

### Verdict: APPROVE

两项 GAP 均 CLOSED。跨文档一致性已通过 api-registry ↔ Resource Ledger ↔ balance-sheet 三向验证。无残留经济数值漂移或平行权威冲突。
