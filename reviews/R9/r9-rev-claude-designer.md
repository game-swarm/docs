# Swarm — R9 Game Designer Review (Claude)

> **Reviewer**: Claude (Opus) — Game Designer seat
> **Round**: R9
> **Source**: reviews/r9-des-summary.md (DESIGN.md, specs/p0/06-08)
> **Date**: 2026-06-14

---

## VERDICT: APPROVE WITH CHANGES

The design is internally coherent, the core loop is sound, and the
Screeps-derived systems (RCL, body parts, special attacks, logistics) form a
genuine strategy space rather than a collection of disconnected mechanics. The
P0-6 feedback-loop framing (LEARN → DECIDE → ACT → UNDERSTAND) is the strongest
part of the document — it treats the *understanding* phase as a first-class
deliverable, which is exactly where programming-game competitors fail.

I am withholding an unconditional APPROVE because several numeric tunables and
two structural gaps will materially shape the player experience and are
currently under-specified or risk creating dominant/dead strategies. None are
architectural blockers; all are resolvable inside P0 with tuning + a few spec
sentences. Hence APPROVE WITH CHANGES rather than REQUEST CHANGES.

---

## Issues

### Critical (must resolve before P0 freeze)

**C1 — Drone lifespan vs. RCL economy is internally inconsistent.**
Lifespan is 1500 ticks (§2). RCL 5 requires 5,000 cumulative progress and RCL 8
requires 150,000 (§3). A single drone physically cannot live long enough to move
a meaningful fraction of high-RCL progress; the entire mid/late economy is
therefore gated on *spawn-loop automation*, not on any in-fiction unit. That is a
legitimate design choice (it's Screeps' choice), but the summary never states
the expected steady-state: how many upgrader drones, at what Work-part count, are
needed to hold vs. advance a Controller against the 5,000-tick downgrade timer
(§3)? Without a target "upkeep curve," we cannot tell whether RCL 8 is reachable
in a 75-minute drone's worth of effort or whether it's a multi-day grind. **Need:
a worked example — "to hold RCL N you must deliver X progress/tick = Y upgrader
bodies" — added to the world-rules spec.** This is the difference between a
satisfying economy and an idle-game treadmill.

**C2 — Body composition irreversibility + 1500-tick lifespan double-punishes
new players, with no mitigation in the NPE.** §2 forbids mid-life part changes
and §11 targets a 5-minute tutorial. A new player's first instinct ("I built the
wrong drone, let me fix it") is impossible by design, and the unit dies in 75
minutes regardless. The tutorial (§11) teaches spawning and harvesting but the
summary lists nothing that teaches *body design as a planning discipline* before
the player is dropped into World. **Need: an explicit tutorial step on body
composition tradeoffs, plus confirmation that `swarm sim` (§11) lets a player
A/B two body designs offline.** Tension #3 in the doc *names* this problem but
the design does not yet *answer* it.

### Major (should resolve in P0; document rationale if deferred)

**M1 — Special-attack counter graph is elegant but two nodes are unfalsifiable
as written.** §6: Fortify is "Countered By: None — it's a buff." A 100-tick ×0.5
self/ally damage reduction with no counter and (per the table) no listed cost
beyond owning a Tough part is a candidate dominant defensive strategy — stack
Fortify uptime and you halve all incoming damage permanently if cooldown < 100.
**The summary lists no cooldown for any special attack.** Hack (capture at <30%
HP), Drain, Overload all need cooldowns or per-tick fuel costs or they become
spammable. **Need: a cooldown/cost column in the special-attack table.** This is
the single most likely source of a degenerate metagame.

**M2 — Overload's "~500k fuel" reduction is a magic number divorced from the CPU
budget it attacks.** §6 says Overload reduces target CPU fuel by ~500k, and §10
shows mods get a 100ms wall-clock budget — but the summary never states the
*player* WASM per-tick fuel budget. If a player's budget is 10M fuel, 500k is a
5% nuisance; if it's 600k, one Overload nearly bricks the target's tick. The
balance of an entire attack category is undefined because the denominator is
missing. **Need: state the player WASM fuel budget and express Overload as a
percentage or a configurable rule.**

**M3 — Storage tax (§7) and Arena fairness (§8) interact in an unexamined way.**
Progressive storage tax kicks in above 30% capacity (§7), but Arena disables the
tax for "competitive fairness" (§8). That means the anti-hoarding mechanism — the
thing that keeps World economies dynamic — is *absent in the mode that is
explicitly ranked and competitive*. Arena will therefore reward turtle-and-bank
strategies that World punishes, splitting the metagame in two. **Need: either an
Arena-appropriate anti-hoard mechanism (match-length is a partial one) or an
explicit design note accepting the divergence.**

**M4 — Damage-type resistance table has an asymmetry that may dead-end two
types.** §5: Tough halves Kinetic *and* Sonic; structures are weak to EMP (×2)
and Corrosive (×1.5). Thermal and Psionic have *no* listed resistance interaction
at all. Thermal therefore reads as "strictly reliable damage with no counter,"
which makes it the default offensive pick, while Psionic exists only to counter
Hack (§6). **Need: confirm Thermal's lack of resistance is intentional (it's the
"can't be tanked" premium type) and that its base damage / cost reflects that,
else it's an auto-include.**

### Minor (polish; safe to defer)

**m1 — "Why idle?" debugger (§11) is the highest-leverage NPE feature and is
listed as a bullet, not a P0 deliverable.** For a programming game, "my drone
does nothing and I don't know why" is the #1 churn driver. Recommend promoting it
to an explicit P0-6 acceptance criterion alongside the per-tick explanation API.

**m2 — Recycle 50% refund (§2) vs. spawn-loop automation (Tension #2) may create
a no-cost churn exploit.** If body parts refund 50% on Recycle and lifespan is
short, the optimal play may be spawn→use→recycle→respawn cycling that games any
per-drone counter. Worth a sentence confirming this is intended or capped.

**m3 — Spectator `spectate_delay` default 0 in World (§9) leaks live intel.**
World replays are private by default, but if `public_spectate` is ever enabled
with delay 0, opponents get real-time vision bypassing fog-of-war. Recommend the
*minimum* enforced delay be > 0 whenever public_spectate is true, mirroring the
Arena ≥100-tick recommendation.

---

## Strengths

1. **The feedback loop is the product.** Treating UNDERSTAND (per-tick
   explanation, "why idle?", replay scrubber, local sim) as a mandatory closed
   quarter of the MVP loop (§1, §11) is the correct and rare insight. Most
   programming games ship the ACT half and bolt on debugging later; this design
   front-loads it. This alone differentiates Swarm.

2. **AI-agents-are-players, not API-callers (§11).** Refusing to add
   `swarm_move`/`swarm_attack` MCP tools and forcing agents to write+deploy WASM
   like humans is a principled decision that keeps the competitive surface
   unified and prevents a two-tier balance problem. Excellent restraint.

3. **World-configurable damage/body/rules (§4, §5, §10).** Pushing balance
   numbers into `world.toml` + Rhai mods rather than hardcoding them means the
   tuning gaps I flag above (C1, M1–M4) are *fixable by config*, not by re-coding
   the engine. The design has built itself the right escape hatch.

4. **Two-layer storage with explicit logistics cost (§7) and three difficulty
   modes** is a clean way to serve both Arena newcomers and Factorio-brained
   hardcore players from one system. The progressive tax + local-stealth +
   no-teleport trio is a thoughtful anti-dominant-strategy package (modulo M3).

5. **The design honestly names its own tensions (§ "Key Design Tensions").**
   Listing lifespan-churn, body irreversibility, and mod power as open risks
   rather than hiding them is exactly the maturity this review process is for. My
   Critical/Major items are mostly *answers owed* to tensions the team already
   identified — which means we're aligned on where the risk lives.

---

## Recommendation to Speaker

Converge on: special-attack cooldown/cost column (M1), player WASM fuel budget
number (M2), and the RCL upkeep worked-example (C1) — these three unblock the
most downstream balance questions and are pure spec additions, no architecture
change. The NPE body-design step (C2) and Arena anti-hoard note (M3) can ride the
same edit pass. Minor items are non-blocking.
