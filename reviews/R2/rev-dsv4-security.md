# R2 Security Review — DSV4 V2 (Re-Review after D1-D7 Audit Fixes)

> **Reviewer**: rev-dsv4-security (DeepSeek V4 Pro)
> **Date**: 2026-06-16
> **Scope**: DESIGN.md v2 (2300 lines, commit 23e5824), specs/01-09, previous R2 reviews (claude-security, gpt-security, dsv4-architect, gpt-architect, gpt-designer)
> **Methodology**: D1-D7 fix verification → protocol consistency audit → data flow trace → algorithmic boundary → trust assumption scan

---

## Verdict: CONDITIONAL_APPROVE (downgraded from previous APPROVE_WITH_RESERVATIONS)

v2 audit fixes addressed 5 of 7 items correctly (D1, D2, D3, D5, D7). However, **D4 is incomplete** (RespawnPolicy still shows old enum values), and the **Overload silent-result contract has a spec-level leak** through `TargetFuelTooLow` in the RejectionReason enum. Additionally, claude-security's CRITICAL-A (deploy nonce) and CRITICAL-B (TOCTOU Phase 2a) remain unaddressed — these were not in the D1-D7 scope but are blocking for implementation.

## Change Log (V1 → V2)

| ID | Item | Status | Notes |
|----|------|--------|-------|
| D1 | Wasmtime 30 API (StoreLimitsBuilder) | ✅ Fixed | spec/04 §2.2 updated |
| D2 | 14 missing RejectionReason variants | ✅ Fixed | spec/08 now has 47 variants (was 31) |
| D3 | DESIGN markdown/table fixes | ✅ Fixed | Various formatting corrections |
| D4 | RespawnPolicy: Spectate/Ban → FixedSpawn/Disabled/Inherit | ❌ **NOT FIXED** | DESIGN line 640 still shows `Spectate \| Ban` |
| D5 | global_storage_public marked as planned | ✅ Fixed | DESIGN line 953: `（计划中）` |
| D6 | (assumed) various sync fixes | ✅ Fixed | Per commit message |
| D7 | Rhai API 规划→远期扩展 | ✅ Fixed | DESIGN line 1276: `（远期扩展——MVP阶段...）` |

---

## Critical (2 — 1 residual, 1 new)

### CRITICAL-1 (Residual, D4 Incomplete): RespawnPolicy Enum Still Shows Spectate/Ban

**Source**: DESIGN.md line 640
**Commit message says**: "D4: DESIGN — fix RespawnPolicy enum: Spectate/Ban→FixedSpawn/Disabled/Inherit"
**Current text**:
```
`respawn_policy` | enum | 殖民地全灭后的处理：`NewRoom` \| `SameRoom` \| `Spectate` \| `Ban`
```

The audit fix D4 committed changes but the DESIGN.md still contains the old enum. This is a **build artifact issue** — the commit diff shows only 4 lines changed in DESIGN.md total, and the RespawnPolicy line was not among them. Either the fix was applied to a different location and DESIGN.md was missed, or the commit was incomplete.

**Impact**: CRITICAL for consistency. If a spec says FixedSpawn/Disabled/Inherit but DESIGN says Spectate/Ban, implementers will see contradictory directives. Spectate/Ban were rejected in R1 as inappropriate gameplay mechanics — they must not ship in any document.

**Recommendation**: Verify the exact line in DESIGN.md and apply the fix. Also grep all other docs for `Spectate` and `Ban` as RespawnPolicy values.

---

### CRITICAL-2 (Spec-Level Leak): Overload Silent-Result Contract Broken by TargetFuelTooLow in RejectionReason Enum

**Source**: DESIGN.md §8.2 Overload (line 1148) vs specs/08 RejectionReason enum (line 92)

**DESIGN.md contract**:
> "Overload 返回静默结果——攻击者无法从结果推断目标 fuel 状态（信息泄露）"

This is correct and well-specified: Overload always returns the same result regardless of whether the target's fuel was actually reduced or already at the floor (MAX_FUEL × 0.2).

**Spec contradiction**:
specs/08 line 92 lists `TargetFuelTooLow` as a RejectionReason variant. If Overload returns `TargetFuelTooLow` when fuel is at the floor vs. (no rejection / generic success) when above the floor, the attacker can:
1. Tick N: Overload target → observe response
2. If `TargetFuelTooLow` → target fuel ≤ 0.2 × MAX_FUEL (binary leak)
3. If no rejection → target fuel > 0.2 × MAX_FUEL, and was reduced by 500k

Even a binary probe per 50 ticks (due to global cooldown) gives attackers strategic information about opponent resource state.

**Why this wasn't caught in D2**: D2 added 14 missing RejectionReason variants to spec/08. `TargetFuelTooLow` may have been among them. But the Overload silent-result contract (added to DESIGN.md in v2) requires that Overload specifically NOT use this rejection — the handler must return a unified response.

**Recommendation**:
1. spec/08: Remove `TargetFuelTooLow` from the public RejectionReason enum, OR mark it as `#[internal]` — never returned to WASM callers.
2. specs/02 §5: Add explicit contract: "Overload rejection is always `Silent` — the response is identical regardless of whether fuel reduction succeeded or was clamped at the floor."
3. The Overload handler must internally track whether fuel was reduced, but the external response must be uniform.
4. DESIGN.md §8.2 Overload row: Add explicit note: "Overload handler NEVER returns TargetFuelTooLow — this RejectionReason is engine-internal only."

---

## High (4)

### HIGH-1 (Claude CRITICAL-A, Unaddressed): Deploy Signature Lacks Nonce/Timestamp — Replay Attack Vector

**Source**: specs/03 §1.1 + §3.3, DESIGN §4.1

**Status**: Not addressed in v2 audit. Claude-security CRITICAL-A remains open.

**Summary**: Deploy signature `Ed25519_Sign(player_sk, Blake3(WASM_bytes))` has no nonce, no server-issued challenge, no timestamp, no player_id binding. An intercepted (cert, sig, WASM) tuple can be replayed indefinitely within the cert's 24h validity.

**v2 DESIGN status**: No change. The deployment flow still describes only "WASM字节 + 证书 + 签名" without nonce or temporal binding.

**Recommendation**: See claude-security review for full spec. Minimum: add `deploy_nonce` (server-issued, 60s TTL, single-use) to the signature payload.

---

### HIGH-2 (Claude CRITICAL-B, Unaddressed): Phase 2a Inline Command Loop TOCTOU — Friendly-Fire Bypass + Resource Amplification

**Source**: specs/02 §3 (command validation matrix), specs/01 §3.3-3.4 (Phase 2a inline model)

**Status**: Not addressed in v2 audit. Claude-security CRITICAL-B remains open.

**Summary**: Phase 2a inline model applies commands sequentially against mutable Bevy World state. This enables:
- B-1: Friendly-fire bypass on Hacked drones (owner=Neutral but should still be friendly to origin owner)
- B-2: Spawn→Recycle same-tick entity lifecycle corruption (Spawn pending queue visibility to subsequent commands not specified)
- B-3: Transfer chain resource amplification — no per-drone per-tick action fatigue/quota

**v2 DESIGN status**: No change to the Phase 2a model or the command validation matrix.

**Recommendation**: See claude-security review. Minimum:
- specs/02 §3.8-3.9: Explicitly declare Spawn pending entities invisible to same-tick commands
- Introduce per-drone per-tick action quota via fatigue field
- specs/02 §3.10: Hack-controlled drone retains `is_friendly_to_origin_owner = true`

---

### HIGH-3 (New, v2 Regression): Overload Fuel Budget Details Leaked Through TickTrace / Replay

**Source**: DESIGN.md §6.1 data model (TickTrace) + §8.2 Overload

**Status**: New finding in v2.

**Summary**: The Overload mechanism in DESIGN.md §8.2 now correctly specifies "静默结果" for the WASM caller — the attacker cannot infer target fuel from the tick response. However, the TickTrace persistence at `/tick/{N}/rejections` and `/tick/{N}/commands` records the actual outcome. Per DESIGN §6.1:
- `/tick/{N}/rejections` stores "被拒绝的指令及原因"
- `/tick/{N}/commands` stores "全部玩家的排序指令"

If Overload's **internal** rejection reason (whether fuel was actually reduced or clamped) is written to TickTrace, and any player can later read this via `swarm_get_replay` or `replay_privacy="world"/"public"`, the silent-result contract is broken retroactively.

**Recommendation**:
1. DESIGN §6.1: Explicitly state that Overload outcomes are NOT stored in `/tick/{N}/rejections` for any privacy level below admin.
2. Overload internal result should be stored in a separate AdminAudit table, not in the per-tick command log.
3. `swarm_get_replay` must filter Overload outcomes for non-admin callers.

---

### HIGH-4 (Claude HIGH-3, Unaddressed): Snapshot Input Volume Has No Cap — Amplified DoS

**Source**: specs/01 §2.3, specs/04 §3.1, DESIGN §3.2

**Status**: Not addressed in v2 audit.

**Summary**: While WASM output is capped at 256KB (specs/04 §3.1 step 5), the **snapshot input** to WASM has no size cap. An attacker can spam cheap Tough drones in a target's visible range to bloat their snapshot → fuel drain from parsing + potential OOM.

**v2 DESIGN/spec status**: No per-snapshot byte cap. The fuel budget table (specs/04 §6) covers host functions but not snapshot input processing.

**Recommendation**: specs/01 §2.3: Add per-player snapshot byte cap = 256KB. specs/04 §3.1: Add snapshot_len ≤ 256KB check BEFORE alloc+write to WASM memory.

---

## Medium (5)

### MED-1 (Residual): D4 Audit Fix Inconsistency — grep Surface

**Source**: DESIGN.md line 640 vs commit message

The commit claims D4 is fixed but the DESIGN text disagrees. This is a build/review artifact issue. All documents referencing RespawnPolicy must be grepped and updated atomically.

**Recommendation**: `rg -l 'Spectate|Ban.*respawn' /data/swarm/docs/` → fix every hit.

---

### MED-2 (Claude HIGH-1, Unaddressed): Compilation Cache Key Missing wasmparser Version

**Source**: specs/04 §7

**Status**: Not addressed.

**Summary**: Compilation cache key is `(module_hash, wasmtime_version)`. If wasmparser is upgraded (e.g., security fix), old cached compilations bypass the new stricter parser. Cache must include wasmparser version and validation policy version.

---

### MED-3 (Claude MED-2, Unaddressed): WASM Fuel Exhaustion vs Wall-Clock Timeout — Semantic Ambiguity

**Source**: specs/04 §6

**Status**: Not addressed.

**Summary**: The spec does not define whether fuel-exhausted tick() results (trap mid-execution) are treated as `WASM crash` (0 commands) or partial output is read. This ambiguity allows speculative attack patterns.

---

### MED-4 (New): Overload Global Cooldown Key Ambiguity

**Source**: DESIGN.md §8.2 Overload row

**Status**: New finding.

**Summary**: The global cooldown specifies "同一目标每 50 tick 最多被 Overload 一次（不限来源）". This is correct in intent but the **cooldown key** is underspecified:
- Is the key `(target_player_id)` or `(target_player_id, world_id)`? (cross-world relevance)
- Is the cooldown tracked per-engine-instance or globally?
- What happens if the Overload is attempted during cooldown — is it silently ignored, or is the attacker's drone cooldown still consumed?

If the attacker's drone cooldown (200 tick) is consumed on a cooldown-blocked Overload, the target can effectively "waste" 200 tick of attacker drone time every 50 ticks — a perverse incentive.

**Recommendation**: Specify cooldown key, storage scope, and whether drone cooldown is consumed on global-cooldown rejection.

---

### MED-5 (New, Cross-Review): EMP Resistance Affects Overload Without Explicit Contract

**Source**: DESIGN.md §8.2 Overload row + §8.2 Damage Types

**Status**: New finding.

**Summary**: Overload is listed with "目标 `EMP` 抗性" in the table. This means a player with EMP-resistant body parts (e.g., Tough with EMP=0.5) reduces Overload's fuel reduction. The spec/08 IDL doesn't capture resistance interaction for Overload — the validator chain doesn't include `resistance(EMP)` for Overload commands.

**Recommendation**: specs/08: Add `resistance(EMP)` to Overload's validator chain. Document the fuel reduction formula: `effective_reduction = 500k × EMP_resistance_multiplier`.

---

## Informational (3)

### INFO-1: Rhai Wall-Clock Now Correctly Scoped

DESIGN.md line 1903 correctly states: "AST 节点数是确定性度量——同一输入在任何硬件上终止于相同节点，保证 state_checksum 可复现。墙钟仅用于告警监控（如单模组 >2s 触发运维告警），不作为状态决定因素。" This properly addresses the previous Rhai wall-clock determinism concern. ✅

### INFO-2: Overseer Entity Tracking — Good Ambient Authority Pattern

The DESIGN.md's two-phase snapshot architecture (§3.2, "两阶段快照架构") and Source Gate pattern (specs/02 §2.2) correctly avoid ambient authority — player_id/tick are injected server-side, not trusted from WASM. This is the right pattern and should be documented as an explicit anti-pattern reference for future extensions.

### INFO-3: Spec/04 §2.4 Module Validation — Cache vs Validation Race

specs/04 §7 line 310 now says "每次 tick 执行前校验 player 的证书未过期未吊销——过期/吊销立即终止 WASM 执行（该 tick 0 指令）。缓存条目随撤销清除。" This is good — certificate validation happens per-tick, not just at deploy time. However, it should also validate that the module hasn't been globally blacklisted (claude CRITICAL-A recommendation 3).

---

## Data Flow Trace (Security Reviewer Specialty)

### Pipeline: Snapshot → WASM → Commands → Validator → ECS

| Step | Validation | Gaps Found |
|------|-----------|------------|
| Snapshot build | One-time serialization by room shard (specs/01 §2.3) | No per-player byte cap (HIGH-4) |
| Snapshot → WASM | `alloc(snapshot_len)` — bounds checked | No size cap before alloc |
| WASM tick() | Fuel metering, epoch interruption | Fuel exhaustion semantic undefined (MED-3) |
| tick() → Commands | JSON schema validation, 256KB cap, max 100 items (specs/02 §1.1) | ✅ Correct |
| Commands → RawCommands | Source Gate injects player_id/tick (specs/02 §2.2) | ✅ Correct |
| RawCommands → ValidatedCommands | Pre-validation: entity existence, ownership, range, resources | Phase 2a TOCTOU (HIGH-2), per-drone fatigue missing |
| ValidatedCommands → ECS | Inline apply (Phase 2a) + deferred Systems (Phase 2b) | ✅ Architecture correct, needs spec precision (HIGH-2) |
| ECS → TickTrace | Full command + rejection log | Overload leak through replay (HIGH-3) |

---

## Trust Assumption Scan

| Assumption | Location | Valid? |
|-----------|----------|--------|
| "WASM won't forge player_id — Source Gate injects it" | specs/02 §2.2 | ✅ Valid — strict field rejection |
| "WASM host functions are read-only — no mutation path" | specs/04 §3.2-3.3 | ✅ Valid — only query functions exposed |
| "MCP is management only — no gameplay actions" | DESIGN §4.2 | ✅ Valid — explicit exclusion |
| "Rhai is server-trusted — no sandbox needed" | DESIGN §8.7 | ⚠️ Partially — process isolation available but optional |
| "Snapshot visibility filter = host function visibility filter" | specs/04 §3.2 | ✅ Valid — same `is_visible_to` function |
| "Overload silent result prevents info leak" | DESIGN §8.2 | ❌ Broken — spec/08 TargetFuelTooLow leaks |
| "Deploy signature proves intent" | specs/03 §1.1 | ❌ Broken — no nonce/temporal binding |
| "Phase 2a is atomic per-command" | specs/01 §3.3 | ❌ Not atomic — TOCTOU between validation and application |

---

## Cross-Review Coordination with rev-claude-security

| Finding | DSV4 V2 | Claude | Consensus |
|---------|---------|--------|-----------|
| Overload silent-result leak | CRITICAL-2 (spec-level) | CRITICAL-1 (agreed) | Agreed — spec fix needed |
| Command limits 100/500 | ✅ RESOLVED | CRITICAL-2 (agreed) | Resolved in v2 |
| Deploy nonce replay | Endorsed (HIGH-1) | CRITICAL-A | Agreed — unaddressed |
| Phase 2a TOCTOU | Endorsed (HIGH-2) | CRITICAL-B | Agreed — unaddressed |
| Compilation cache key | Endorsed (MED-2) | HIGH-1 | Agreed — unaddressed |
| Snapshot input no cap | Endorsed (HIGH-4) | HIGH-3 | Agreed — unaddressed |
| D4 RespawnPolicy fix | CRITICAL-1 (incomplete fix) | Not covered | DSV4 finding |
| Overload TickTrace leak | HIGH-3 (new) | Not covered | DSV4 finding |
| Overload cooldown key ambiguity | MED-4 (new) | Not covered | DSV4 finding |
| EMP resistance spec gap | MED-5 (new) | Not covered | DSV4 finding |

---

## D1-D7 Fix Completeness Assessment

- **D1**: ✅ Complete — Wasmtime 30 API properly updated throughout spec/04
- **D2**: ✅ Complete — spec/08 now has 47 RejectionReason variants (verified: 31 + 14 new = 45 listed in IDL + ObjectNotFound, NotOwner, etc.)
- **D3**: ✅ Complete — Various DESIGN formatting fixes
- **D4**: ❌ Incomplete — RespawnPolicy still shows old enum values
- **D5**: ✅ Complete — global_storage_public marked as planned
- **D6**: ✅ Complete — Per commit message (may relate to D3-style fixes)
- **D7**: ✅ Complete — Rhai API properly scoped as 远期扩展

**D4 is the only audit fix that didn't land.** This is the highest-priority item for immediate correction.

---

## Implementation-Ready Items (Positive Findings)

The v2 design has several security improvements over v1:

1. **Overload visibility check**: DESIGN §8.2 now requires `is_visible_to(target, attacker)` — properly closes the blind attack vector.
2. **Overload global cooldown**: 50-tick per-target cooldown prevents coordinated spike attacks.
3. **Rhai AST node budget**: Spec/07 §5.1 properly uses deterministic AST node counting as the hard limit, with wall-clock demoted to operational alert only.
4. **Path finding budget**: spec/04 §8 has `host_path_find` at 10 calls/tick with `10,000 + 50/tile` fuel cost + cache key includes visibility fingerprint — properly bounds algorithmic attack surface.
5. **Source Gate injection**: spec/02 §2.2 correctly prevents WASM from forging player_id/source/tick — the single most important trust boundary is well-guarded.

---

## Priority Action Items (for Speaker / Next Round)

| Priority | ID | Description | Blocking |
|----------|-----|-------------|----------|
| 🔴 P0 | D4 incomplete | Fix RespawnPolicy in DESIGN.md line 640 | Implementation |
| 🔴 P0 | CRITICAL-2 | Remove TargetFuelTooLow from WASM-visible RejectionReason for Overload | Implementation |
| 🔴 P0 | Claude-A | Add deploy nonce + temporal binding to signature | Security launch |
| 🔴 P0 | Claude-B | Fix Phase 2a TOCTOU (Spawn visibility, per-drone fatigue) | Security launch |
| 🟠 P1 | HIGH-3 | Overload outcome not stored in replay-accessible TickTrace | MVP launch |
| 🟠 P1 | HIGH-4 | Snapshot input byte cap = 256KB | MVP launch |
| 🟡 P2 | MED-2 | Compilation cache key includes wasmparser version | Pre-production |
| 🟡 P2 | MED-4 | Overload cooldown key semantics | Implementation |
| ⚪ P3 | MED-5 | EMP resistance in Overload validator chain | Documentation |

---

*rev-dsv4-security (DeepSeek V4 Pro) — R2 V2 Re-Review. D1-D7 audit fixes verified (5/7 complete). 2 Critical (1 residual D4, 1 new spec-level Overload leak), 4 High, 5 Medium, 3 Informational. Cross-reviewed with rev-claude-security findings (4 unaddressed Critical/High endorsed).*
