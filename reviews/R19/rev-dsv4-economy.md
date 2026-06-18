# R19 Closure Verification — Economy/Numerical Review (DSV4)

> **Reviewer**: rev-dsv4-economy
> **Date**: 2026-06-18
> **Scope**: Verify R18 Blocker + R18 User Decisions are closed. Economy/numerical domain only.
> **Authority Source**: `specs/reference/game_api.idl.yaml` (canonical); `specs/core/08-resource-ledger.md` §2 (economic single source)

---

## 1. Overall Verdict: **APPROVE**

All economy-scope items (B6, D3, D4) verified CLOSED. Single-source economic authority is established and consistently referenced. One minor documentation polish note on gameplay.md §Drone lifecycle — non-blocking.

---

## 2. Item-by-Item Judgment Table

### R18 Consensus Blockers

| ID | Status | Evidence |
|----|--------|----------|
| **B1** | N/A | Not economy domain. YAML/Markdown consistency is architecture/API scope. Observed: api-registry.md claims auto-generation from game_api.idl.yaml (line 1-3); YAML and Markdown both show 35 RejectionReason codes, 46 MCP tools — structurally consistent. |
| **B2** | N/A | Not economy domain. RejectionReason closure is API/validation scope. Observed: 35 canonical codes defined in both YAML and Markdown with debug_detail field (512 bytes) and detail_level enum. |
| **B3** | N/A | Not economy domain. MCP tool namespace consolidation is API scope. |
| **B4** | N/A | Not economy domain. Tick/Trace/Persistence architecture is engine scope. |
| **B5** | N/A | Not economy domain. Security fields in machine source is security/API scope. |
| **B6** | **CLOSED** | Economic single-source authority established. `specs/core/08-resource-ledger.md` §2 declares itself "唯一经济权威" (line 62). `economy-balance-sheet.md` §5 and line 3 both reference Resource Ledger as sole authority. `gameplay.md` §8 economy classification table references Resource Ledger for Recycle, Storage Tax, and Upkeep. **Minor note**: gameplay.md line 106 says "回收 drone 获得 50% 资源退还" (flat 50%) without lifespan-proportional qualification — but the authoritative formula in Resource Ledger §2.3 correctly defines the proportional 10–50% range. All economic sections defer to Resource Ledger, making this a documentation polish issue, not a gap. |
| **B7** | N/A | Not economy domain. Capacity contract provability is security/engine scope. |

### R18 User Decisions

| ID | Status | Evidence |
|----|--------|----------|
| **D1** | N/A | Not economy domain. api-registry.md full generation is API/documentation scope. |
| **D2** | N/A | Not economy domain. RejectionReason canonical+debug_detail is API scope. |
| **D3** | **CLOSED** | Recycle refund lifespan-proportional formula (10–50%) fully defined in Resource Ledger §2.3: `recycle_refund = body_cost × remaining_lifespan / total_lifespan × recycle_refund_base / 10000`, clamped to minimum `recycle_refund_min = 1000 bp (10%)`, with `recycle_refund_base = 5000 bp (50%)`. All basis points, no floats. Tutorial override (`tutorial_recycle_refund_full_ticks = 500`) documented. economy-balance-sheet.md §5 references Resource Ledger as authority. |
| **D4** | **CLOSED** | Storage tax tiered 0/1/5/20 bp consistently defined across all documents. Resource Ledger §2.1: `storage_tax_tiers = [(30,0),(60,1),(85,5),(100,20)]`. Resource Ledger §2.2: full tiered formula with example calculation (75% storage = 105/tick). gameplay.md §8 "累进存储税" table: identical tiers. economy-balance-sheet.md §1: references Resource Ledger. No inconsistencies found. |
| **D5** | N/A | Not economy domain. Blob async upload is persistence/engine scope. |
| **D6** | N/A | Not economy domain. soft_launch 3-phase PvP is gameplay/PvP scope. Verified the transition mechanism exists in gameplay.md §8 "soft_launch 后 PvP 渐进过渡" — but per scope constraint, do not evaluate. |
| **DA1** | N/A | Not economy domain. deploy_mutation replay_class is deploy/engine scope. |
| **DA2** | N/A | Not economy domain. f64→定点 is numerical representation scope. Observed: Resource Ledger §6 declares `ResourceAmount: i64`, `ResourceRate: i64`, `FeeBps: u16` — all fixed-point types. gameplay.md §8.8 "Determinism Contract" line 1961: "禁 f64，游戏引擎数值用 i64 × 精度因子". Consistent. |
| **DA3** | N/A | Not economy domain. Worker pool 256 default is infrastructure/engine scope. Observed: api-registry.md §5.5: `max_pool = 256`. Confirmed present. |

---

## 3. Economic Single-Source Verification (B6 Detail)

The Resource Ledger (`08-resource-ledger.md`) §2 is established as the single economic authority. Cross-document consistency check:

| Economic Concept | Resource Ledger § | economy-balance-sheet.md | gameplay.md §8 | Consistency |
|------------------|--------------------|--------------------------|----------------|-------------|
| Empire Upkeep formula | §Empire Upkeep: `base_upkeep × rooms × (1 + rooms / room_soft_cap)` | §1: Same formula, references RL | §8.7: Rhai mod formula (different mechanism — mod system, not hardcoded). Note: gameplay line 1948 acknowledges two formula systems coexist — vanilla hardcoded (RL authority) vs Rhai empire-upkeep mod (configurable). Both are present by design. | Consistent (dual-path design) |
| Recycle refund | §2.3: `body_cost × remaining_lifespan / total_lifespan × 5000/10000`, min 10% | §5: References RL "(lifespan 10%–50%)" | §8 table: "Recycle \| Unlock \| +50% 原 spawn 成本" — simplified description | Minor simplification in gameplay, RL is authority |
| Storage tax tiers | §2.1: `[(30,0),(60,1),(85,5),(100,20)]` | §1: References RL | §8 table: 0/1/5/20 bp | Fully consistent |
| Global transfer fees | §2.1: deposit 100bp, withdraw 500bp | References RL | §8: 1%/5% | Fully consistent |
| Allied transfer | §2.1: fee 200bp, delay 200t, cooldown 500t, daily cap 10k | References RL | N/A (allied transfer is RL concern) | Consistent |

**Verdict**: Single-source model is functional. All documents that define economic parameters defer to Resource Ledger. The one simplification in gameplay.md line 106 (Recycle "50%" without proportional qualification) does not create a conflict — it's descriptive prose in the drone lifecycle section, not a competing parameter definition. No blocking gap.

---

## 4. Recycle Formula Mathematical Verification (D3 Detail)

Given a drone with body cost = 800 Energy, total_lifespan = 1500:

| Remaining Lifespan | Lifespan % | Raw Refund (bp formula) | Clamped | Refund Energy |
|--------------------|------------|------------------------|---------|---------------|
| 1500 (fresh) | 100% | 800 × 1500/1500 × 5000/10000 = 400 | ≥ 80 (10% min) | **400 (50%)** |
| 750 (half) | 50% | 800 × 750/1500 × 5000/10000 = 200 | ≥ 80 | **200 (25%)** |
| 300 (20%) | 20% | 800 × 300/1500 × 5000/10000 = 80 | ≥ 80 | **80 (10%)** |
| 150 (10%) | 10% | 800 × 150/1500 × 5000/10000 = 40 | ≥ 80 | **80 (10%)** — floor kicks in |
| 75 (5%) | 5% | 800 × 75/1500 × 5000/10000 = 20 | ≥ 80 | **80 (10%)** — floor |

Formula is well-defined. No division-by-zero edge case — lifespan is always ≥ MIN_LIFESPAN (default 100). No floating point — all basis points integer arithmetic. Convergence at both ends (100%→50% refund, <20%→10% floor).

---

## 5. Storage Tax Equilibrium Verification (D4 Detail)

Full tiered formula from Resource Ledger §2.2, with capacity = 1,000,000:

| Storage Amount | Storage % | Tier 0 (0bp) | Tier 1 (1bp) | Tier 2 (5bp) | Tier 3 (20bp) | Total Tax/tick |
|---------------|-----------|--------------|--------------|--------------|---------------|----------------|
| 100,000 | 10% | 0 | 0 | 0 | 0 | **0** |
| 450,000 | 45% | 300k × 0 = 0 | 150k × 1bp = 15 | 0 | 0 | **15** |
| 750,000 | 75% | 300k × 0 = 0 | 300k × 1bp = 30 | 150k × 5bp = 75 | 0 | **105** |
| 950,000 | 95% | 300k × 0 = 0 | 300k × 1bp = 30 | 250k × 5bp = 125 | 100k × 20bp = 200 | **355** |
| 1,000,000 | 100% | 0 | 30 | 125 | 150k × 20bp = 300 | **455** |

Tax curve is monotonically increasing, convex (marginal rate increases with storage), creating a natural disincentive against hoarding without a hard cap. Tutorial mode exempt (免税). Arena mode also exempt by default. All parameters configurable via `world.toml`.

---

## 6. Anti-Snowball Mechanism Verification

The Resource Ledger defines three economic anti-snowball mechanisms. Mathematical soundness:

| Mechanism | Formula Location | Convergence? | Notes |
|-----------|-----------------|--------------|-------|
| Empire Upkeep | RL §Empire Upkeep: O(n × (1+n/cap)) ≈ O(n²) | ✅ Convergent | 50-room upkeep = 15,000/tick vs 1-room upkeep = 55/tick — 273× difference for 50× rooms. Net outflow exceeds income at ~50 rooms (economy-balance-sheet §2.4). |
| Storage Tax | RL §2.2: tiered convex | ✅ Convergent | Marginal rate increases from 0→1→5→20 bp. At 100% storage, tax = 455/tick on 1M capacity. Prevents infinite hoarding without hard cap. |
| Recycle proportional | RL §2.3: lifespan-dependent | ✅ No arbitrage | Recycle always returns ≤ spawn cost. Minimum 10% floor prevents zero-refund exploit. No way to profit from spawn→recycle→spawn cycle. |

No mathematical gaps found. All formulas use integer arithmetic (basis points), no floating point. Deterministic execution order in RL §4 guarantees consistent application.

---

## 7. CrossCheck — Recommended Verifications for Other Reviewers

The following items were observed in documents but are outside economy scope. Recommend other reviewers verify:

1. **B1 (YAML vs Markdown consistency)** → rev-speaker or rev-reviewer: api-registry.md claims auto-generation from game_api.idl.yaml. Verify the generation pipeline is in place (not just a manual copy). The changelog in api-registry.md §变更记录 shows v0.3.0 as "generated from YAML" — confirm tooling exists.

2. **B7 (Capacity contract provability)** → rev-reviewer: Resource Ledger §8 references `design/engine.md` §3.4.2 for capacity contracts. Economy domain defers to engine domain. Recommend engine reviewer verify the capacity limits in api-registry.md §5 are provably enforceable in the tick pipeline.

3. **DA2 (f64→定点)** → rev-reviewer: Resource Ledger §6 uses `i64`/`u16` types. gameplay.md §8.8 declares "禁 f64". However, api-registry.md MCP tool output schemas still show `f64` for `swarm_get_economy` (income, expenses, storage_tax, maintenance) and `swarm_get_resources` (income_rate). This is a presentation-layer concern (MCP wire format vs internal engine math) — recommend API reviewer verify intent.

---

## 8. Summary

- **Economy-scope items**: B6, D3, D4 — all **CLOSED**
- **Non-economy items**: B1-B5, B7, D1-D2, D5-D6, DA1-DA3 — all **N/A** (outside economy domain)
- **Blockers**: None in economy domain
- **Verdict**: **APPROVE**
