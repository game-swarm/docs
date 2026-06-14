# R10 — Game Designer Review (Claude Opus 4.8)

> **Reviewer**: Claude Opus 4.8 · Game Designer
> **Source**: reviews/r10-des-summary.md
> **Date**: 2026-06-14 · Phase 0 freeze

---

## VERDICT: **APPROVE** (Phase 0 freeze ready)

The design is internally coherent and the core loop is sound. The "code *is* the strategy" pillar, the unified human/AI code path, and the world-configurable rules engine form a strong, differentiated foundation. No Critical or blocking issues found at the design level. The tensions below are tuning/UX concerns to carry into Phase 1, not freeze blockers.

---

## Strengths

1. **Unified player path** — humans and AI agents both write+deploy WASM, no `swarm_move`/`swarm_attack` shortcut for AI. This is the right call: it keeps the game one game, prevents a balance fork, and makes AI a first-class citizen rather than a bolt-on.

2. **Closed feedback loop is mandated, not aspirational** — P0-6 forces all four LEARN→DECIDE→ACT→UNDERSTAND steps for MVP. The per-tick rejection-reason API ("Move within 1 tile, or use RangedAttack range 3") and the "Why idle?" debugger directly attack the #1 churn risk for a programming game: silent failure.

3. **World-configurable damage/resource types** — treating damage types like resource types (data, not code) with the two-layer resistance model (component × attribute) is elegant and gives modders real power without engine forks.

4. **Three logistics modes** — shipping no/light/hardcore logistics is a mature accessibility lever; it lets the same engine serve Arena newcomers and Factorio-brained veterans.

5. **Determinism discipline in mods** — forbidding clock/entropy/IO in Rhai, recording all `actions` in TickTrace, and the 10-tick auto-disable safeguard show the replay/audit requirement was designed in, not patched on.

---

## Issues (non-blocking — Phase 1 tuning)

**[Major] Lifespan + body-irreversibility compound on new players.**
1500-tick lifespan forces spawn-loop automation *and* body composition is locked at spawn *and* tutorial 100% refund expires at 500 ticks. Three "you must already know what you're doing" gates stack on the same early window. The 500-tick refund cliff lands right when players graduate from tutorial — exactly when they make their first expensive body mistakes in the live world. **Recommend**: extend full-refund window or tie it to player progression (first N spawns) rather than a hard tick count.

**[Major] Hack ownership transfer is permanent and swingy.**
A successful Hack at <30% HP transfers a drone permanently. For a unit the victim invested 600+ Energy (Claim part) into, permanent loss with no buy-back creates feel-bad swings, especially in persistent World mode where it compounds over hours. Psionic resistance is the only counter. **Recommend**: consider a recapture/decay window or a "captured drones cost upkeep / die faster" rule so Hack is disruptive but not a permanent economy swing.

**[Minor] Damage-type × resistance combinatorics risk body-building paralysis.**
Six damage types, two component resists each, plus dynamic attribute resists, plus six special attacks tied to parts — the optimal-body decision space is large and the body is irreversible. This is depth, but for new players it's opaque. **Recommend**: the strategy dashboard should surface "what killed your drones, by damage type" so players learn the matrix empirically rather than from a table.

**[Minor] Engine cannot validate economic coherence.**
Costs reference resource names by string, so a world can define a body part costing a resource no source produces (noted in tension #8). A `swarm world validate` lint that flags unreachable-cost parts and orphan resources would catch broken custom worlds before players hit a soft-lock.

**[Minor] Arena code-lock has no escape hatch.**
Locking code at match start is competitively clean but a mid-match bug is unfixable for up to ~4h. **Recommend**: at minimum communicate the lock loudly in UI; optionally a single limited patch window early in the match.

---

## Open question for Speaker

Storage tax is *disabled* in Arena for "competitive fairness" but *active* in World. Is hoarding-as-dominant-strategy actually acceptable in Arena's fixed 5000-tick window, or does disabling the tax there reintroduce the very turtle/hoard meta the tax exists to prevent? Worth confirming this is intentional and not just a World-vs-Arena symmetry default.

---

*R10 · Game Designer · APPROVE with Phase-1 tuning notes*
