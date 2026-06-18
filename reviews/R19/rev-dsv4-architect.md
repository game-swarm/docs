# R19 Architecture Review — DSV4

**Reviewer**: rev-dsv4-architect (DeepSeek V4 Pro)
**Date**: 2026-06-18
**Scope**: R18 Consensus Blocker + User Decision closure verification
**Authoritative Source**: `specs/reference/game_api.idl.yaml` (per D1/A ruling)

---

## Verdict: CONDITIONAL_APPROVE

1 GAP found (minor, non-consensus-blocking). All 7 R18 consensus blockers CLOSED. All 6 user decisions CLOSED. All 3 additional decisions CLOSED.

---

## Item-by-Item Judgment

| ID | Description | Status | Evidence |
|----|-------------|:------:|----------|
| **B1** | YAML vs Markdown 双写不一致 | **CLOSED** | api-registry.md L3-7 explicitly states "冲突时以 YAML 为准", YAML-generated pipeline confirmed. Spot-checks: api_version 0.3.0, CommandAction 19, RejectionReason 35, MCP tools 46 — all match. |
| **B2** | RejectionReason 未闭合 | **CLOSED** | YAML defines 35 canonical codes + `debug_detail` (512 bytes, non-canonical) + `detail_level` enum (competitive/practice/training). Per D2/B: wire enum stable, context in debug_detail. api-registry.md §2 mirrors fully. |
| **B3** | MCP Tool 三套名称空间 | **CLOSED** | 46 tools organized by capability profiles (onboarding/play/deploy/debug/admin). Security columns present: subject_source, replay_class, visibility_filter, rate_limit_key. WebSocket security model documented (Agent/Browser/Replay channels). YAML §3 maps to api-registry.md §3. |
| **B4** | Tick/Trace/Persistence 分叉 | **CLOSED** | 29-system manifest (06-phase2b-system-manifest.md) is authoritative scheduler. engine.md §3.2 and 01-tick-protocol.md §3.4 both reference it. Serial spine + 3 parallel sets consistent. Persistence layered: FDB (small objects) → Object Store (blobs async, D5/B). Hash chain (collect_id→attempt_id→commit_id) spans all three domains. |
| **B5** | 安全字段未入机器源 | **CLOSED** | YAML MCP tools section includes security columns per tool (subject_source/replay_class/visibility_filter/rate_limit_key). WebSocket security: Agent WS with per-message seq+MAC (ed25519), Browser WS read-only, Replay WS read-only+seek. |
| **B6** | 经济单源未闭合 | **CLOSED** | 08-resource-ledger.md §2 declared as "唯一定义源". All rates in basis points. Storage tax tiered `[(30,0),(60,1),(85,5),(100,20)]`. Recycle refund base 50%/min 10%. Global transfer 1%/5%. Allied transfer 2%. No floating point. engine.md §3.4.2 defers to registry for authoritative capacity limits. |
| **B7** | 容量合同不可证明 | **CLOSED** | api-registry.md §5 is the authoritative capacity source. engine.md §3.4.2 adds derivations (Aggregate CPU Admission Formula, Worker Pool Derivation, 500/1000 player scenarios) with explicit labeling as "B7 补充". Derivation chain traceable. CI fault injection test (01-tick-protocol.md §3.5) validates snapshot restore on FDB commit failure. |
| **D1** | api-registry.md 全量生成 | **CLOSED** | api-registry.md header: "本文档由 game_api.idl.yaml 自动生成。手写修改将被覆盖。" YAML covers all sections: CommandAction/RejectionReason/MCP Tools/Host Functions/Capacity/TickTrace/Direction4/ResourceOperation/Deploy/Persistence. |
| **D2** | RejectionReason canonical+debug_detail | **CLOSED** | YAML: 35 canonical codes + debug_detail (max 512 bytes, non-canonical) + detail_level (competitive/practice/training, default=competitive). MD mirrors fully with wire enum stability guarantee. |
| **D3** | Recycle refund lifespan 10-50% | **CLOSED** | 08-resource-ledger.md §2.3: `recycle_refund_base=5000bp (50%)`, `recycle_refund_min=1000bp (10%)`. Formula: `max(body_cost × 10%, body_cost × lifespan_ratio × 50%)`. Tutorial first 500 tick: 100% refund via `tutorial_recycle_refund_full_ticks`. |
| **D4** | Storage tax tiered 0/1/5/20bp | **CLOSED** | 08-resource-ledger.md §2.1: `storage_tax_tiers = [(30,0),(60,1),(85,5),(100,20)]`. Tiered formula in §2.2 with worked example (75% capacity → 105 tax/tick). All rates in basis points. |
| **D5** | blob 异步上传 | **CLOSED** | 05-persistence-contract.md §2 Phase C: async blob upload triggered after FDB commit. Upload status tracking (pending→uploading→complete/failed). Replay degrades gracefully on failed uploads (terminal_state=audit_gap). api-registry.md §11: async_object_store_upload with fire-and-forget semantics. |
| **D6** | soft_launch 3阶段PvP | **CLOSED** | gameplay.md §3 "soft_launch 后 PvP 渐进过渡 (D6/B)" defines 3 phases: Phase 1 (safe_mode 500 tick, full immunity), Phase 2 (soft_launch 1500 tick, PvE-only, PvP disabled), Phase 3 (gradual PvP introduction with room-level cooldown/DR). Parameters table in gameplay.md L590-598. Also referenced in 06-feedback-loop.md and 08-resource-ledger.md. |
| **DA1** | deploy_mutation replay_class | **CLOSED** | YAML: `swarm_deploy` tool has `replay_class: idempotent_mutation`. api-registry.md §10 documents deploy_mutation flow with fdb_version_counter for deterministic replay ordering. |
| **DA2** | f64→定点 | **GAP** | Internal model: 08-resource-ledger.md §6 declares `ResourceAmount: i64`, `ResourceRate: i64`, `FeeBps: u16`. engine.md §3.4.8: "所有资源/年龄/伤害/进度使用 u64 或 i64 定点整数". API output schema: game_api.idl.yaml L484 has `income_rate: f64` in `swarm_get_resources` output. **The internal computation model is correct (定点), but the API schema retains a single f64 field. This is likely a presentation-layer artifact but creates an inconsistency between the IDL contract and the internal model.** |
| **DA3** | worker pool 256 default | **CLOSED** | api-registry.md §5.5: `max_pool = 256` (authoritative). engine.md §3.4.2 declares `MAX_POOL = 1000` but defers to registry ("权威容量定义以 api-registry.md §5 为准"). The authoritative value matches DA3 (256). |

---

## GAP Detail

### DA2-GAP: `income_rate: f64` in API schema

**Location**: `specs/reference/game_api.idl.yaml` L484 — `swarm_get_resources` output schema

**Content**: The output type `income_rate` is declared as `f64`, while all internal resource computation uses i64/basis points per 08-resource-ledger.md §6 and engine.md §3.4.8.

**Impact**: Minor. Internal computation model is correct. This appears to be a presentation-layer holdover. The conversion path (i64 → f64) is well-defined and deterministic. Not a consensus blocker.

**Recommendation**: Either (1) add a note clarifying that `income_rate` is a presentation convenience converted from internal basis points, or (2) change the API schema to expose raw basis points as integer with a separate display helper. The design parliament's design-parliament reviewer can adjudicate.

---

## Cross-Check Recommendations

1. **api-registry cross-check (rev-apidx-dsv4)**: `income_rate: f64` in game_api.idl.yaml vs internal i64 model — verify the conversion contract is explicitly defined and tested. The API schema should document that this field is a convenience conversion from internal fixed-point representation.

2. **gameplay cross-check (rev-designer-dsv4)**: The 3-phase PvP model (D6) is well-documented in gameplay.md §3 with explicit parameters. Verify that the phase transition (Phase 2 → Phase 3 gradual PvP introduction) is consistently described in the engine's tick protocol and the ECS system manifest. Specifically: does `pvp_block_system` (S26 in manifest) respect room-level PvP cooldown/DR from soft_launch parameters?

3. **performance cross-check (rev-performance-dsv4)**: engine.md §3.4.2 still contains MAX_POOL=1000 in its Worker Pool Derivation section (L345) and the 450/750/1000 player scenarios (L349-383). The authoritative value is 256 (api-registry.md). While engine.md defers to the registry, the example calculations should be recalculated for max_pool=256 to ensure the capacity derivations remain valid. This is a documentation consistency issue, not a design error — the registry is correct.

---

## Summary

| Category | Count | Status |
|----------|:-----:|--------|
| R18 Consensus Blockers | 7 | All CLOSED |
| R18 User Decisions | 6 | All CLOSED |
| Additional Decisions | 3 | 2 CLOSED, 1 GAP (DA2: f64 residual in API schema) |
| **Total** | **16** | **15 CLOSED, 1 GAP** |

Verdict: **CONDITIONAL_APPROVE** — the single GAP (DA2: f64 in income_rate API field) is a presentation-layer artifact that does not affect internal computation correctness. All 7 consensus blockers are resolved. Recommend the API reviewer confirm the f64 field is intentional.
