# R25 Closure Verification — Architect (DeepSeek V4 Pro)

> **Scope**: R24 残留 B2/B3 GAP 闭合验证。仅验证，不发现新问题。

---

## B2-GAP: API/经济单事实源

**R24 问题**: 经济数据（storage tax thresholds, upkeep, Recycle 比例）分散在多处，无单事实源。

### 验证项 1: Storage tax thresholds (10K→30% capacity)

**状态**: CLOSED

**证据**:
- `api-registry.md` §5.7「Economy 限制」将 storage tax 定义为 **percentage-based tiers**: 30%/60%/85% capacity，非绝对值。
- `api-registry.md` §10.2「Economy Resource Operations」: `StorageTax` 操作描述为 "Percentage-based tiered tax on global storage. Tiers: 0%–30% = 0 bp, 30%–60% = 1 bp, 60%–85% = 5 bp, 85%–100% = 20 bp."
- `api-registry.md` §10.3「Canonical Formulas」: 公式为 `storage_pct = stored_total / storage_capacity × 100`，按百分比分段计税。
- 每处均标注权威引用: `specs/core/08-resource-ledger.md` §2.2 authoritative tiered formula。

**结论**: 旧绝对值阈值 (10K) 已完全替换为百分比阈值 (30%/60%/85% capacity)，api-registry.md 为权威源，引用指向 resource-ledger.md。

### 验证项 2: Gameplay upkeep (-40~-3,150→reference)

**状态**: CLOSED

**证据**:
- `api-registry.md` §10.2: `UpkeepDeduction` 定义为 **公式** "Empire-wide superlinear upkeep: `base_upkeep × rooms × (1 + rooms / room_soft_cap)`"，非硬编码数值。
- 标准默认值: `base_upkeep=50, room_soft_cap=10` 以参数形式声明（非固定范围 -40~-3,150）。
- 权威引用: `specs/core/08-resource-ledger.md` §Empire Upkeep。

**结论**: 旧硬编码 upkeep 数值 (-40~-3,150) 已替换为带参数的公式，api-registry.md 为权威源，引用指向 resource-ledger.md。

### 验证项 3: Recycle 退还比例

**状态**: CLOSED

**证据**:
- `02-command-validation.md` §3.18「Recycle 比例退还与 lifespan 约束」: 公式 `refund_pct = max(0.1, 0.5 × (remaining_lifespan / total_lifespan))`，范围 [10%, 50%]，非固定 50%。
- `api-registry.md` §10.2: `RecycleRefund` 描述为 "Lifespan-proportional partial refund. Formula: `max(1000, (remaining_lifespan * 5000) / total_lifespan)` bp → clamp [1000, 5000] bp = [10%, 50%]."
- `api-registry.md` §10.3: 公式步骤完整，舍入策略 floor。
- `api-registry.md` §0「Fixed-Point Type Registry」: 全部使用 basis points / u64 定点整数，无 f64。

**结论**: 旧固定 50% 退还已替换为 lifespan-proportional 公式（10%–50%），api-registry.md 为权威事实源。

### B2 总评

三项经济数据均已收敛到 `api-registry.md` 为权威事实源，公式/阈值统一为百分比/参数形式，不再存在硬编码绝对值分散问题。

**B2: CLOSED** ✅

---

## B3-GAP: 特殊攻击优先级唯一权威

**R24 问题**: `02-command-validation.md` 与 `06-system-manifest.md` 各有一份特殊攻击优先级表，冲突。

### 验证项 1: 02-command-validation 已删除冲突表

**状态**: CLOSED

**证据**:
- `02-command-validation.md` §3.16「同 tick 多命中优先级」:
  - 标注 **"R24 B3-GAP 修复"**。
  - 明确声明: "特殊攻击优先级以 `06-phase2b-system-manifest.md` §S14 为唯一权威。此处不再重列可冲突的优先级顺序。"
  - 禁止复制: "实现者必须以此为准，不得从本文档复制/粘贴优先级链。"
- 旧优先级表已完全移除，替换为指向 manifest 的引用。

**结论**: 冲突表已删除，明确指向 manifest §S14 为唯一权威。

### 验证项 2: 06-system-manifest S14 标注唯一权威链

**状态**: CLOSED

**证据**:
- `06-phase2b-system-manifest.md` §S14「special_attack_reducer」:
  - 优先级链: **Hack > Drain > Overload > Debilitate > Disrupt > Fortify**
  - 附带声明: **"唯一权威优先级链"** — "此为 Swarm 引擎中该优先级链的唯一定义——`02-command-validation.md` 已删除旧优先级表"
  - 6 步完整执行管线: Parallel collect → Merge sort → Reducer resolve → Deliver → Status advance → Damage application
- `06-phase2b-system-manifest.md` §「Special Attack Unique Writer Contract」:
  - 每种 StatusState component 有且仅有一个 writer system（all point to `status_adv` S22）
  - `PendingIntents` buffer 唯一 writer 为 `spec_atk_red` S14
  - Damage from special attack 唯一 writer 为 `dmg_apply` S15
- 并发写入结构: S11-S13 per-system sub-buffer（线程局部，无竞争）→ S14 serial collector → canonical `pending_intents`

**结论**: S14 为特殊攻击优先级的唯一权威定义，附带显式唯一权威声明，冲突文档引用已清除。

### B3 总评

`02-command-validation.md` 冲突表已删除 → S14 为唯一权威优先级链 → 唯一 writer contract 确保无多路径写入冲突。

**B3: CLOSED** ✅

---

## Verdict

| GAP | 状态 | 关键证据文件 |
|-----|------|-------------|
| B2: API/经济单事实源 | **CLOSED** | api-registry.md §5.7, §10.2, §10.3 |
| B3: 特殊攻击优先级唯一权威 | **CLOSED** | 06-manifest §S14; 02-cmd-val §3.16 |

### APPROVE

两项 GAP 均已正确闭合。经济数据收敛到 api-registry.md 为单事实源（百分比阈值、公式化 upkeep、lifespan-proportional Recycle）。特殊攻击优先级收敛到 06-system-manifest §S14 为唯一权威链，02-command-validation 冲突表已删除并标注禁止复制。

**零残留 GAP。无发现新问题（符合 Closure Verification 约束）。**
