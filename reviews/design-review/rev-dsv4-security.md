# Security Design Review: Swarm

**Reviewer**: Security Reviewer (rev-dsv4-security)
**Date**: 2026-06-15
**Request**: Game design review — anti-snowball, fairness, exploit vectors, trust model
**Scope**: DESIGN.md + P0-1 through P0-9 specs
**Method**: Protocol consistency analysis, data-flow tracing, race-condition detection, trust-boundary mapping

---

## VERDICT: CONDITIONAL_APPROVE

The design is fundamentally sound. The three-tier trust model (WASM → Rhai → Rust), deferred command
pipeline, source-gate architecture, and deterministic seed-shuffle fairness mechanism together form
one of the strongest security foundations I have seen in an MMO game design document. The
progressive storage tax, drone lifespan, and logistics transport time are elegant anti-snowball
mechanisms.

However, five issues demand design-level attention before implementation, and five more warrant
close scrutiny in later phases. None are showstoppers, but resolving them now prevents
architectural lock-in of the wrong tradeoffs.

---

## STRENGTHS (what is done well)

### S1. Three-Tier Trust Model Is Cohrent and Well-Bounded

The WASM → Rhai → Rust layering (§8.7) is correctly designed:

| Tier | Trust | Isolation | Verdict |
|------|-------|-----------|---------|
| WASM (player code) | Untrusted | Process isolation + seccomp + cgroups + fuel metering + fork-per-tick + no-network namespace | Excellent |
| Rhai (mod code) | Server-trusted | AST budget + actions cap + 100ms wall-clock timeout with transaction rollback | Good (see C2) |
| Rust (engine) | Immutable core | Deterministic ECS, fixed PRNG, same Wasmtime pinned version | Excellent |

The deferred command model (§5, P0-4 §3) is the linchpin: WASM never mutates world state directly.
It returns JSON, which is validated, and only then applied. This is a textbook "never trust the
client" design.

### S2. Source Gate Prevents Privilege Escalation

P0-9's source matrix explicitly declares which sources can submit gameplay commands. The
`player_id` is server-injected — clients cannot self-report it. The `MCP_Deploy` source is denied
gameplay submission at the Source Gate. No single bypass path exists.

### S3. Anti-Refund-Amplification Design Is Thorough

P0-2 §7's refund model with cross-tick deferral, deploy-reset rule, per-source deduplication, and
three-tick throttle is well-thought-out. The "退还不进同一 tick" constraint prevents the most
obvious compute-amplification attack.

### S4. Deterministic Seed Shuffle + Fuel Metering = Structural Fairness

Player execution order is determined by a Blake3 XOF from `(tick_number, world_seed)`, producing a
deterministic but unpredictable shuffle. Combined with WASM instruction counting instead of
wall-clock time, this provides language-agnostic fairness that Screeps never achieved.

### S5. Progressive Storage Tax + Transport Time

The three-pronged anti-hoarding mechanism (progressive tax, local stealth advantage, transport
latency) is well-designed in principle and addresses the "rich get richer" problem that plagues
persistent MMO economies.

### S6. WASM Sandbox Hardening Is Comprehensive

P0-4 specifies: seccomp whitelist (blocking open/socket/fork/clock_gettime/getrandom), cgroup v2
memory/CPU/pid limits, empty network namespace, per-tick fork+kill lifecycle, Wasmtime fuel
metering, epoch interruption, 5MB module limit, import whitelist, StartSection rejection,
256KB output cap. The malicious WASM sample library with CI integration closes the test gap.

### S7. Tick Failure Semantics Are Fully Modeled

P0-1 §6 covers 9 distinct failure modes with clear recovery strategies. The degraded mode
(3 consecutive abandons → pause joins + block deploys → auto-recover after 10 clean ticks)
is a well-designed circuit breaker.

---

## CRITICAL ISSUES (must resolve before/early in implementation)

### C1. Controller Lifespan Cliff: 2 Controllers = Finite, 3 Controllers = Immortal

**Location**: DESIGN.md L530 controller maintenance model

The drone lifespan maintenance rule:

> "玩家拥有的每个 Controller 每 tick 给全局所有 drone 回退 age 0.5 tick"

Drone age increases by 1 per tick (natural aging). Each Controller subtracts 0.5 from *all* drones
globally. This creates an abrupt cliff:

| Controllers | Net age change/tick | Drone lifespan |
|-------------|---------------------|----------------|
| 0 | +1.0 | ~1,500 ticks |
| 1 | +0.5 | ~3,000 ticks |
| 2 | +0.0 | ~infinite (age stays flat) |
| 3+ | -0.5 ~ -N×0.5 | infinite + reverse aging |

A player with 2 controllers can keep all drones alive indefinitely (age never reaches 1500).
A player with 3 controllers makes drones *younger* over time, effectively resetting their age to 0.

**Impact**: This creates a binary "have enough controllers / don't" gate rather than a smooth
scaling curve. Players who capture their 3rd room get a discontinuous power jump — all their
existing drones become immortal in a single tick. This is the opposite of anti-snowball design:
it *rewards* reaching critical mass with a permanent, uncounterable advantage.

**Recommendation**: Replace linear per-controller subtraction with a diminishing-returns model.
Options:
- (a) Cap the total age reduction at ~80% of natural aging (so drones always eventually die),
      requiring periodic replacement regardless of empire size.
- (b) Make age reduction per-drone rather than global: each Controller reduces age by 0.5 tick,
      but the reduction is split across all drones owned. 3 Controllers × 0.5 = 1.5 ticks/day
      total reduction, distributed across 500 drones → negligible per-drone effect.
- (c) Tie age reduction to Controller *level*: a level-1 Controller reduces age by 0.1, level-8
      by 0.5. This makes the maintenance curve smooth and requires continued investment.

### C2. Rhai Mod Side-Effect Blast Radius Is Unbounded

**Location**: DESIGN.md §8.7 Rhai API, tick_end.rhai example

The Rhai mod API exposes `deduct_resource`, `award_resource`, `damage_entity`, and
`set_entity_flag` — all with `player_id` targeting. A single Rhai mod (installed by the server
owner, ostensibly "trusted") has unrestricted write access to all players' resources and entities.

The 100ms timeout with transaction rollback (§8.7) mitigates infinite loops, but a mod that
completes in 99ms can still cause catastrophic damage:

```rust
// Rhai code — executes in 5ms, drains every player to zero
for player in state.players() {
    actions.deduct_resource(player.id, "Energy", player.resources().get("Energy"));
}
```

**Why this matters**: The trust model states "Rhai = server owner trusts the mod author." But
in practice, server owners install mods from a community marketplace. The marketplace review
process (§8.7) relies on "社区 review + rating" — which is social, not technical. A malicious
mod could be disguised as a benign utility.

**Recommendation**:
- (a) Add per-mod resource mutation caps in `mod.toml`: `max_deduct_per_tick = N`,
      `max_award_per_tick = N`, `max_damage_per_tick = N`.
- (b) Require explicit opt-in for per-player resource mutation: Rhai mods should not have
      access to `deduct_resource` by default; they must declare `capability = "resource_mutation"`
      in their manifest.
- (c) Add a dry-run mode for mod installation: run the mod against a snapshot, verify that
      per-player resource deltas are within expected bounds.

### C3. Local Storage Tax Evasion: The Stealth Paradox

**Location**: DESIGN.md §8.2, "本地存储隐匿性" and progressive tax table

The progressive storage tax applies only to **global** storage. Local storage is explicitly
exempt and given a "stealth advantage" — enemy players cannot see local storage contents.
This creates an incentive inversion:

> Players are *punished* for using global storage (taxed, partially visible) and *rewarded*
> for hoarding in local storage (untaxed, invisible).

A large empire with many Storage buildings (capacity 1,000,000 units each) can hoard unlimited
resources locally at zero tax, completely bypassing the intended anti-snowball mechanism. The
5% transfer cost from global→local is a small friction, not a deterrent for established players.

**Recommendation**:
- (a) Apply the progressive tax to *total* storage (global + local combined), using a lower
      rate for local storage to preserve the strategic advantage (e.g., local storage taxed
      at 20% of the global rate).
- (b) Cap local storage per room based on Controller level, creating a natural ceiling on
      tax-free hoarding.
- (c) Alternatively, acknowledge this as intentional design (the "Strategy Depth" column
      in the logistics mode table) and document the tradeoff explicitly, rather than
      presenting the tax as a complete anti-hoarding solution.

---

## HIGH ISSUES (should resolve before Arena mode ships)

### H1. Overload Team-Collusion Grief in Competitive Modes

**Location**: P0-2 §3.14, DESIGN.md §8.2 Overload attack

Overload reduces a target player's fuel budget by 500k per hit (5% of MAX_FUEL=10M), down to a
floor of 20% (2M). In a 1v1 Arena match, this is strong but balanced. However:

- **No range limit**: Overload has no spatial range restriction — it's a "logical attack."
- **Stackable across attackers**: Multiple players can target the same player.

In a free-for-all Arena or World PvP, N players coordinating against one target can reduce that
player to 20% fuel budget in a single tick (N × 500k → capped at 8M reduction). A player at
20% fuel has severely degraded AI capability, making them an easy target for follow-up attacks.

**Recommendation**: 
- (a) Add an Overload resistance that builds up: each Overload hit in the same tick against
      the same target has diminishing effect (e.g., 500k → 250k → 125k → 0).
- (b) Give Overload a room-based range constraint, bringing it in line with other attacks.
- (c) Add a per-target per-tick Overload cap (e.g., max 2 Overloads per target per tick).

### H2. WASM Certificate Expiry During Tick = Silent Turn Loss

**Location**: P0-4 §7 (module cache), P0-3 §1.1 (24h cert expiry)

The spec states:

> "每次 tick 执行前校验 player 的证书未过期未吊销——过期/吊销立即终止 WASM 执行（该 tick 0 指令）"

A player whose 24-hour certificate expires at tick boundary receives 0 commands with no warning.
Their drones stand idle for the entire tick. In Arena mode, a single missed tick can be
match-deciding.

**Recommendation**:
- (a) Add a 5-minute grace period after cert expiry during which execution continues normally
      but the player receives a "renew certificate" notification.
- (b) Auto-renew certificates for active players (those who submitted commands in the last
      N ticks) without requiring re-authentication.
- (c) At minimum, surface the cert expiry timestamp via MCP and Web UI so players/AI agents
      can proactively refresh.

### H3. No Controller Re-Claim Cooldown After Abandonment

**Location**: DESIGN.md L237 (controller downgrade)

> "若 Controller 失去 owner 超过 downgrade_timer（默认 5000 tick），降一级"

A player can abandon a room (removing their owner claim on the Controller), let the timer tick
down for 4,999 ticks, then re-claim it with no penalty. The downgrade timer resets to 5000 on
re-claim. This enables "feint" strategies where a player temporarily abandons territory to
lure enemies in, then re-claims before downgrade.

More importantly, there's no cooldown on *repeated* claim-abandon cycling. A player could use
this to repeatedly trigger "Controller claimed" events (for mods that award resources on claim)
or to reset the downgrade timer indefinitely.

**Recommendation**: Add a `reclaim_cooldown` parameter (default: 1000 ticks) — a Controller that
has been abandoned cannot be re-claimed by the same player until the cooldown expires. This
preserves the strategic feint possibility while preventing abuse.

### H4. Rhai Cross-Mod Resource Depletion Interaction

**Location**: DESIGN.md §8.7, mod dependency/conflict declarations

The mod.toml supports `dependencies` and `conflicts` declarations, but these are static (mod
author declares them). Two independently-installed mods that each deduct resources could
interact additively in ways the mod authors never anticipated.

Example: Mod A (empire-upkeep) deducts `drone_cost × drones` Energy. Mod B (weather-effects)
deducts `storm_penalty × drones` Energy. Neither declares a conflict with the other because
their authors never tested them together. A player with 500 drones gets hit by both → bankrupt
in a single tick.

**Recommendation**:
- (a) Add a per-player, per-tick total resource deduction cap as a world-level parameter
      (e.g., `max_total_deduction_per_tick_pct = 25%`).
- (b) Run the mod registry through a combinatorial cost analysis at install time: calculate
      worst-case per-player resource deltas and warn the server owner if they exceed thresholds.

### H5. Drain Swarm Attack Surface

**Location**: P0-2 §3.13, DESIGN.md §8.2 Drain special attack

Drain has a 50-tick cooldown *per drone*. A player with 500 drones, each with 10 Carry parts
(500 carry capacity per drone), can field a rotating Drain swarm. If 10% of drones (50) perform
Drain in a staggered rotation, they extract 50 × 500 = 25,000 units per tick from enemy storage
continuously — for a cost of 50 × 200 = 10,000 Energy per tick.

A fully upgraded Storage holds 1,000,000 units. At 25,000 units/tick drain rate, it's emptied
in 40 ticks (~2 minutes of real time). The defending player has very limited counterplay
(build Towers? Fortify?).

**Recommendation**:
- (a) Add diminishing returns on Drain against the same target structure within a tick window
      (e.g., each successive Drain on the same target is 20% less effective).
- (b) Add a "theft alarm" mechanic: when a structure loses > N% of resources in a single tick,
      the owner receives a notification via the snapshot.
- (c) Make Drain affected by Tower defensive fire (Towers auto-attack enemy drones in range).

---

## MEDIUM ISSUES (address before production)

### M1. World Seed Compromise Enables Tick-Order Prediction

The seeded shuffle uses `Blake3(tick_number || world_seed)`. The world_seed is 256-bit and
rotates every 10,000 ticks — strong in principle. However:

- The seed is stored in FoundationDB. Any admin with FDB access can read it.
- The 10,000-tick rotation means a leaked seed is valid for ~8.3 hours (at 3s/tick).
- During that window, an attacker can predict every player's tick order.

**Recommendation**: Encrypt the seed at rest in FDB using a key derived from a hardware-bound
secret (TPM or AWS KMS). The seed rotation alone doesn't address the leak window.

### M2. In-Transit Resource Transfer Visibility

During `transfer_to_global_time` (default 10 ticks), resources are "in transit" and "可被敌方
巡逻 drone 拦截". The design does not specify whether in-transit transfers are visible to other
players' drones (via snapshot or host_get_objects_in_range).

- If visible: attackers can precisely target interception. This makes global storage transfers
  extremely risky, pushing players toward 100% local storage (exacerbating C3).
- If invisible: interception becomes probabilistic (patrol and hope) rather than targeted.

**Recommendation**: Explicitly specify the visibility of in-transit transfers in the visibility
policy (P0-5). Recommend: visible but only within a limited range (e.g., 3 tiles from the
transfer route midpoint).

### M3. Snapshot JSON Serialization DoS Surface

At 500 drones per player, each with multiple components (Position, Drone, Owner, body parts),
the snapshot JSON for a single player could be several megabytes. The snapshot is serialized
once per room, then filtered per player — but in a room with 10 players each at the 500-drone
cap, the room-level serialization handles 5,000 entities.

The design specifies:
- Output JSON ≤ 256KB from WASM (P0-4 §6)
- Snapshot per player is the same as what `tick()` receives

But the input snapshot size to WASM `tick()` is not explicitly capped in the specs. If snapshot
serialization takes > 100ms for large rooms, it eats into the COLLECT phase budget (2,500ms
total), creating a DoS vector: players deliberately create many entities to slow down snapshot
generation for everyone.

**Recommendation**: Add a snapshot size cap per player (e.g., 512KB) with entity count
prioritization (closest entities first). Document this in P0-1 §2.3.

### M4. Spawn Body Order Sensitivity to Resource Price Arbitrage

Body parts have fixed resource costs. If a world defines multiple resource types (e.g., Energy
at high regeneration + Matter at low regeneration), players will optimize spawns using whichever
resource is cheapest. The design handles this correctly at the engine level (generic
`HashMap<ResourceName, Amount>`), but the *economic balance* can be trivially broken by
asymmetric resource availability.

This is not a code bug but a game-balance concern: the engine has no mechanism to prevent
degenerate spawn compositions when resource costs are poorly tuned.

**Recommendation**: Add a `body_part_cost_validation` pass at world configuration load time
that checks for obvious imbalance (e.g., a body part costing only the most abundant resource
while providing high combat value). This could be a warning rather than a hard error.

### M5. Controller Safe Mode as Infinite Grief Protection

The Controller has `safe_mode` (remaining ticks) and `safe_mode_available` (remaining uses).
During safe mode, the room is presumably invulnerable to attacks (the exact mechanics aren't
specified in the design doc, but the term implies protection). 

Questions the design doesn't answer:
- How many safe mode uses does a player start with?
- How do they recharge? (Time-based? Resource cost? Never?)
- What's the cooldown between uses?

In Screeps, safe mode is finite and expensive. Without constraints, it becomes a "pause PvP"
button that owners of large empires can use to become untouchable.

**Recommendation**: Specify safe mode economics. Recommend: max 1 active use + 1 reserve,
recharging at 1 use per 20,000 ticks (~16 hours). Cost: significant global resources.

---

## INFORMATIONAL (design notes, not blockers)

### I1. Recycle 100% Refund in Tutorial — Isolation Must Be Watertight

Tutorial worlds return 100% of spawn cost on Recycle (vs 50% in standard). The isolation
between Tutorial and standard worlds must be absolute. The `Tutorial` source in P0-9 correctly
specifies "独立 namespace" for global storage, but this needs rigorous enforcement at the
engine level: no cross-world resource transfer, no shared global storage namespace, no drone
migration between Tutorial and standard worlds.

### I2. path_find Cache Key Design Is Excellent

P0-4 §8: cache key includes `player_visibility_fingerprint` — ensuring players with different
fog-of-war states see different cache entries. This prevents a timing side-channel where one
player could infer another's visibility by measuring path_find cache hit rates. Well caught.

### I3. Combat "Damage First, Heal After" Ordering

P0-1 §3.4: `combat_system` processes damage before heals in the same tick. This means a drone
at 1 HP that receives both an attack (30 damage) and a heal (12 HP) in the same tick dies
(damage applied first → HP reaches 0 → death_mark, then heal has no target). This is a
deliberate design choice with significant gameplay implications — worth documenting explicitly
as "simultaneous attacks kill before heals can save" in the game rules visible to players.

### I4. Fortify Is the Only Unresistable Combat Action

Fortify (P0-2 §3.17) has no resistance check — "增益+净化，不受抗性影响". This makes it
universally reliable as a counter to ALL debuffs (Debilitate, Drain, Overload, Hack). In a
game where every other special attack has a counterplay resistance type, Fortify's unresistable
nature is an asymmetry worth noting. It effectively creates a "rock-paper-scissors" where
Fortify beats everything defensively. This is probably intentional (it's expensive: 400 Energy,
300 tick cooldown), but ensure it's a conscious choice.

### I5. Body Part Irreversibility + 50% Recycle Creates a "Commit Tax"

Body parts are immutable once spawned. Recycle returns 50% (100% in Tutorial). The 50%
"respec tax" in standard worlds is a meaningful economic friction. Players who misconfigure
their drone body lose half their investment to fix it. This is appropriate for a strategy game
(rewards planning over trial-and-error), but it will generate player frustration. Consider
a "respec window" — e.g., first 100 ticks after spawn, Recycle returns 90%.

---

## TRUST MODEL COHERENCE — FULL CHAIN ANALYSIS

```
Source          Trust    Sandbox     Capability       Validation
──────────────────────────────────────────────────────────────────
WASM (player)    ZERO    Process     → JSON only      Source Gate + Command Pipeline
                          isolation   (no mutation)    + Schema validation
                          + seccomp                    + Entity ownership checks
                          + cgroup                     + Range/distance checks
                          + fuel                       + Resource checks
                          + epoch

MCP_Deploy       Auth    Gateway     → deploy WASM     Rate limited (10/h)
                          rate-limit   only             Token scope check
                                                        Cert validation

MCP_Query        Auth    Gateway     → read world      Rate limited (50/tick)
                          rate-limit   state only       Token scope check
                                                        Visibility filter

Rhai (mod)      TRUSTED  Engine      → mutate world    AST budget (10k)
                 (owner   embedded     via actions      Actions cap (100)
                  choice)                              Wall-clock (100ms)
                                                        Transaction rollback
                                                        Mod conflict declarations
                                                        Auto-disable after 10 fails

Admin            Auth+   Gateway     → full access     Token scope check
                 Audit                             Dual-signature for Rollback
                                                        Complete audit log

Replay           System  Engine      → read-only       Source: Replay
                                                        No gameplay commands
```

**Boundary enforcement is complete**. No source can escalate its capabilities without passing
through an explicit gate. The weakest link is the Rhai tier (see C2), where the gap between
"trusted by server owner" and "installed from community marketplace" creates a non-trivial
residual risk.

---

## VERIFICATION CHECKLIST

These are items the design *claims* but that must be verified in implementation:

- [ ] `player_id` is NEVER readable from client-provided fields in any command path
- [ ] WASM StartSection rejection works before any user code executes
- [ ] Snapshot visibility filter (`is_visible_to`) is the SAME function used for host function results
- [ ] Tutorial world global storage is in a SEPARATE FDB key prefix, not just a different namespace string
- [ ] Refund credit is cleared when a new module hash is detected (deploy-reset rule)
- [ ] Rhai transaction rollback actually reverses all in-memory state (not just DB)
- [ ] `path_find` cache is invalidated when terrain changes in the relevant area
- [ ] Seed rotation at 10,000 tick boundaries doesn't create a deterministic-replay gap
- [ ] Certificate expiry during tick execution is handled BEFORE snapshot generation (to fail fast)
- [ ] Dragonfly cache staleness never serves as an authority for gameplay decisions

---

## SUMMARY TABLE

| ID | Severity | Area | Issue | Recommendation |
|----|----------|------|-------|----------------|
| C1 | Critical | Anti-Snowball | Controller maintenance cliff: 2→3 = immortal drones | Diminishing returns model |
| C2 | Critical | Trust Model | Rhai mod unrestricted resource mutation | Capabilities manifest + per-mod caps |
| C3 | Critical | Anti-Snowball | Local storage tax exemption incentivizes hoarding | Tax total storage, lower rate for local |
| H1 | High | Fairness | Overload team-collusion grief (no range, stackable) | Diminishing effect or per-target cap |
| H2 | High | Trust Model | Cert expiry mid-tick = silent 0-command loss | Grace period or auto-renewal |
| H3 | High | Anti-Snowball | No re-claim cooldown after controller abandonment | Add reclaim_cooldown parameter |
| H4 | High | Trust Model | Rhai cross-mod resource depletion interaction | Per-player deduction cap or combinatorial analysis |
| H5 | High | Fairness | Drain swarm attack surface (25k units/tick) | Diminishing returns on same target |
| M1 | Medium | Fairness | Seed leak enables 8h tick-order prediction | Encrypt seed at rest |
| M2 | Medium | Exploit | In-transit transfer visibility unspecified | Specify in visibility policy |
| M3 | Medium | Exploit | Snapshot serialization DoS surface | Add per-player snapshot size cap |
| M4 | Medium | Exploit | Spawn body resource price arbitrage | World-config load-time balance validation |
| M5 | Medium | Fairness | Controller safe mode economics unspecified | Specify finite, slow-recharging safe mode |

---

*End of review. All findings are based on the design documents as of 2026-06-15 (Phase 0 Architecture Freeze, R14).*
