# R25 Closure Verification — API/DX (DeepSeek V4 Pro)

Date: 2026-06-19
Reviewer: rev-dsv4-apidx
Task: R25-dsv4-apidx
Scope: Verify R24 B2/B3 GAP closure only. No new findings allowed.

---

## B2-GAP: API/Economy Single Source of Truth

> R24 identified: storage tax thresholds hardcoded as absolute (10K units); upkeep numbers
> (-40~-3,150) hardcoded without canonical reference; Recycle rate was ¥2.3 flat.

### B2.1 Storage Tax Thresholds: 10K → 30% Capacity

**Verdict: CLOSED**

Evidence:

| Source | Evidence |
|--------|----------|
| `api-registry.md` §5.7 | `Storage tax tier 1 threshold = 30% capacity` — percentage-based, not absolute units |
| `api-registry.md` §10.2 | `Tiers: 0%–30% cap = 0 bp, 30%–60% = 1 bp, 60%–85% = 5 bp, 85%–100% = 20 bp` — all percentage of capacity |
| `08-resource-ledger.md` §2.2 | `storage_tax_tiers = [(30,0),(60,1),(85,5),(100,20)]` — canonical tier definition, percentage-based |
| `economy-balance-sheet.md` §1 | "存储税使用 Resource Ledger §2.2 tiered 公式...以下场景中的存储税数值均由此公式导出" — defers to canonical source |

The storage tax has been converted from an absolute 10,000-unit hardcoded threshold to a percentage-of-capacity tiered system. All four documents cross-reference consistently. The Resource Ledger (§2.2) is the single mathematical authority. The Economy Balance Sheet (§5) explicitly defers rather than re-declaring.

### B2.2 Gameplay Upkeep: Hardcoded Ranges → Canonical Reference

**Verdict: CLOSED**

Evidence:

| Source | Evidence |
|--------|----------|
| `api-registry.md` §10.2 | `UpkeepDeduction`: `base_upkeep × rooms × (1 + rooms / room_soft_cap)`. "Per `specs/core/08-resource-ledger.md` §Empire Upkeep." |
| `08-resource-ledger.md` §Empire Upkeep | Canonical formula with parameter table: `base_upkeep=50`, `room_soft_cap=10` (Standard). Defines tiered execution order (§4 step 1). |
| `economy-balance-sheet.md` §1 | "维护费公式由 `specs/core/08-resource-ledger.md` §Empire Upkeep 权威定义。经济报表引用此公式，不重新声明。" — explicit deferral |
| `economy-balance-sheet.md` §5 | "Resource Ledger 为所有收支计算的单一权威源。本文档只做数值验证和模式对比，不重新定义费率或公式。" |

The old hardcoded upkeep ranges (-40 to -3,150) have been replaced by a formula-based system with a single authoritative source (Resource Ledger §Empire Upkeep). The balance sheet retains illustrative computed values but explicitly marks them as derived from the canonical formula, not independently authoritative. The Resource Ledger's execution order (§4) places UpkeepDeduction as step 1, enforcing single-source-of-truth.

### B2.3 Recycle: ¥2.3 Flat → Lifespan-Proportional 10-50%

**Verdict: CLOSED**

Evidence:

| Source | Evidence |
|--------|----------|
| `api-registry.md` §10.2 | `RecycleRefund`: `max(1000, (remaining_lifespan * 5000) / total_lifespan)` bp → clamped to [10%, 50%] |
| `api-registry.md` §10.3 | Canonical formula: `refund_rate_bp = max(1000, (remaining_lifespan * 5000) / total_lifespan)`, `refund_amount = (refund_rate_bp * body_cost) / 10000` |
| `08-resource-ledger.md` §2.5 | `recycle_refund_base = 5000 bp (50%)`, `recycle_refund_min = 1000 bp (10%)`. Formula: `body_cost × remaining_lifespan / total_lifespan × recycle_refund_base / 10000` |

The old flat ¥2.3 (23%) rate has been replaced by a lifespan-proportional formula with 10-50% range using basis points. The canonical formula is defined in Resource Ledger §2.5 and cross-referenced consistently in api-registry.md. All three sources agree on the formula and parameters.

### B2 Summary

All three sub-items are CLOSED:
- Storage tax: absolute 10K → percentage tiers ✓
- Upkeep: hardcoded ranges → formula with canonical reference ✓  
- Recycle: flat 23% → lifespan-proportional 10-50% ✓

---

## B3-GAP: Special Attack Priority Uniqueness Authority

> R24 identified: 02-command-validation contained a duplicate priority table conflicting with
> 06-system-manifest S14; S14 needed explicit uniqueness authority chain annotation.

### B3.1 02-command-validation: Conflict Table Deleted

**Verdict: CLOSED**

Evidence:

| Source | Evidence |
|--------|----------|
| `02-command-validation.md` §3.16 header | "**R24 B3-GAP 修复**：特殊攻击优先级以 `06-phase2b-system-manifest.md` §S14 为唯一权威。此处不再重列可冲突的优先级顺序。" |
| `02-command-validation.md` §3.16 body | "同一 tick 内同一目标被多个特殊攻击命中时，优先级由 `special_attack_reducer` (S14) 按 canonical priority sort 裁决。**权威优先级链见 `specs/core/06-phase2b-system-manifest.md` §1（System Schedule 注释）和 §S14 reducer 实现**。实现者必须以此为准，不得从本文档复制/粘贴优先级链。" |

The old duplicate priority table has been removed from 02-command-validation.md. The document now contains an explicit R24 B3-GAP fix annotation, and directs all readers to the single authority (06-phase2b-system-manifest.md §S14) with an enforcement clause: "实现者必须以此为准，不得从本文档复制/粘贴优先级链" (implementers MUST use that source, must NOT copy/paste the priority chain from this document).

### B3.2 06-system-manifest S14: Uniqueness Authority Chain Annotated

**Verdict: CLOSED**

Evidence:

| Source | Evidence |
|--------|----------|
| `06-phase2b-system-manifest.md` §S14 step 3 | "本次 reducer resolve：同一 target 的多个 intent 按**唯一权威优先级链**裁决：**Hack > Drain > Overload > Debilitate > Disrupt > Fortify**（此为 Swarm 引擎中该优先级链的唯一定义——`02-command-validation.md` 已删除旧优先级表）；冲突 intent 降级记录" |
| `06-phase2b-system-manifest.md` §Special Attack Unique Writer Contract | Maps each Status Component to its single writer system. `PendingIntents` buffer → sole writer `spec_atk_red` (S14). |
| `06-phase2b-system-manifest.md` §S14 processing pipeline | Full 6-step pipeline: Parallel collect → Merge sort → Reducer resolve → Deliver to S22 → Status advance (S22) → Damage application (S15). Complete execution contract. |

S14 now carries:
1. The **unique authority annotation**: "此为 Swarm 引擎中该优先级链的唯一定义" (this is the ONLY definition of this priority chain in the Swarm engine).
2. A cross-reference confirming 02-command-validation has deleted its old table.
3. The **Unique Writer Contract** showing S14 is the sole writer of `PendingIntents` buffer — no other system can write this state, establishing a verifiable single-authority chain.
4. A complete 6-step processing pipeline that makes the authority chain traceable end-to-end.

### B3 Summary

Both sub-items are CLOSED:
- 02-command-validation: old conflict table deleted, replaced with explicit deferral + enforcement clause ✓
- 06-system-manifest S14: uniqueness authority annotation ("唯一定义"), sole writer contract, traceable pipeline ✓

---

## Verdict: APPROVE

Both R24 residual GAPs are fully closed:

| GAP | Status | Key Evidence |
|-----|--------|-------------|
| B2 (Economy single source) | CLOSED | Storage tax → percentage tiers; Upkeep → formula with Resource Ledger canonical reference; Recycle → lifespan-proportional 10-50% bp formula |
| B3 (Special attack priority authority) | CLOSED | 02-command-validation deleted conflict table; S14 annotated as sole priority chain definition with Unique Writer Contract |

No residual gaps. No new findings per closure verification protocol.
