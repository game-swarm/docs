# Game Design Review — Swarm Engine
**Reviewer**: Claude (Game Designer perspective)  
**Date**: 2026-06-14  
**Sources**: `design/DESIGN.md` + `specs/p0/` (01–09)

---

## VERDICT

**APPROVE WITH CONDITIONS**

This is a technically sophisticated and philosophically coherent design. The core thesis — "your code is your army" — is well-executed and meaningfully differentiated from Screeps. The architecture is sound and the Phase 0 freeze is genuinely complete. Conditions to address before Phase 1 ships are noted below.

---

## Issues

### CRITICAL

**[C1] No drone lifecycle / age cap defined**
`Drone.age: u32` exists in the ECS struct but no maximum lifetime, decay curve, or death condition is specified anywhere in the P0 specs. DESIGN §3.1 lists the field but neither P0-2 nor P0-8 defines what happens when age increments. Does the drone live forever? Die at 1500 ticks like Screeps? This is a core loop invariant — players cannot write correct spawning logic without it, and the `decay_system` in P0-1 §3.3 is listed in ECS order but never defined. Blocks Phase 1.

**[C2] Controller upgrade path completely absent**
`Controller` has `level`, `progress`, `progress_total`, `downgrade_timer`, and `safe_mode` fields (DESIGN §3.1), but no spec defines how you upgrade it, what `progress_total` values are at each level, what structures become available per level, or what the `downgrade_timer` countdown means in practice. This is the entire Room Control Level (RCL) progression system — the primary long-term goal structure for persistent world play. Without it there is no sense of advancement. Blocks World mode.

**[C3] Body part cost table missing from IDL**
P0-8 IDL references `registry.body_cost(body)` for Spawn cost, but no base costs for individual body parts appear in the IDL itself. DESIGN §8.3 world.toml shows `body_part.Move = { Energy = 50 }` as a configuration example, but the *default* values for a standard world are never canonically defined. The TypeScript example in DESIGN §8.5 calls `registry.cost("spawn")` but there is no authoritative baseline table that SDK generators can use. Codegen will be incomplete.

---

### HIGH

**[H1] Win/loss condition for World mode is undefined**
DESIGN §10 describes World mode as "not pursuing fairness" and lists metrics like "colony age, GCL, room count — for display only." But there is no defined end state, no explicit statement that World is endless, and no clarity on what "losing" means (all Spawns destroyed → what happens? `respawn_policy` covers re-entry, but what is the emotional beat?). Players need to understand the implicit goal. Without this, onboarding will be confused — the tutorial (P0-6 §2.1) ends with "deploy to World or try Arena" but doesn't explain what you're trying to accomplish in World.

**[H2] Fatigue mechanics underspecified**
`Drone.fatigue: u32` appears in the struct and the Move validator checks `fatigue == 0`, but nowhere in any spec is the fatigue generation formula defined. How much fatigue does a MOVE part generate per step? How does terrain (Swamp vs Plain) affect it? How fast does it decay per tick? This directly affects pathfinding strategy and is referenced in P0-6 §5.2 ("Fatigued: 12% of common errors") implying it's a real player pain point, yet it's unspecified.

**[H3] Arena scoring system not specified**
P0-6 §6 states Arena win condition is "destroy enemy Spawn, or higher score at time limit" but "score" is never defined. Is it GCL? Room count? Resource held? Drone kills? This matters enormously for how players code their strategy. A score-based Arena with resource scoring plays completely differently from one with kill scoring. The ranked league system (Human/WASM, AI-assisted, AI tournament) in P0-6 §6 also has no matchmaking or ELO/rating spec.

**[H4] `safe_mode` interaction with PvP is unspecified**
`Controller` has `safe_mode`, `safe_mode_available`, and `safe_mode_cooldown` fields. Safe mode is a defensive mechanic (inherited from Screeps) that should temporarily disable enemy attacks in a room. But P0-5 visibility policy, P0-2 command validation, and DESIGN §8 combat rules make no mention of safe mode at all. If it's present in the data model, the behavior needs to be defined — or the fields should be removed to avoid confusion.

**[H5] Cross-room movement is absent**
The entire game is structured around rooms (`RoomId` in Position, Controller per room, multi-room empire building) but there is no spec for how drones move between rooms. What happens at a room boundary? Is there a door tile? A portal? Does the drone simply teleport to the adjacent room's entrance? This is fundamental to the multi-room progression loop and affects pathfinding (P0-2 §4.3 PathFind limits to "same room").

**[H6] Global storage "in transit" interception is a Phase 6 promise with Phase 1 data model impact**
DESIGN §8.4 states resources in transit between local and global storage "can be intercepted by enemy patrol drones (requires PvP enabled, Phase 6 combat system)." This is a significant game mechanic that requires a distinct data state (`TransitResource` component or similar). If the data model doesn't account for it now, retrofitting it in Phase 6 will require migration. The IDL (P0-8) has `TransferToGlobal`/`TransferFromGlobal` commands with a `duration` field but no representation for the in-transit resource as a world entity.

---

### MEDIUM

**[M1] No spec for Tower behavior**
Tower appears in `StructureType` enum, in vision range table (P0-5: range 3, charged 6), and in world.toml cost examples, but there is no spec for what a Tower *does*. Does it auto-attack? Require a command? What is its damage, range, and energy consumption? This is a key defensive structure referenced in the tutorial ("place a Tower at (5,3) to defend") but completely unspecified mechanically.

**[M2] Rhai module `actions.deduct_resource` can cause negative resources — handling is implicit**
P0-7 §4 shows `resources.get(res_name) < 0` as a condition in `memory_upkeep_system`, implying resources can go negative. DESIGN §8.7 says `onshortfall = "degrade"/"damage"/"despawn"` for the empire-upkeep mod. But the general rule for what happens when *any* Rhai action drives a resource below zero is not defined. Does it clamp at zero? Go negative? Trigger forced entity removal? The `deduct_resource` API surface needs a defined underflow contract.

**[M3] Drone env_vars / memory is poorly named and confusingly documented**
The `env_vars` / `memory_size` system (DESIGN §8, P0-7) conflates two concepts: "environment variables" (labeled `drone.set("role", "harvester")`) and "drone memory" (labeled in bytes with spawn/upkeep costs). In Screeps, `Memory` is a per-player persistent JSON object. Here it seems to be per-drone. The naming (env_vars + memory_size in bytes) is inconsistent — env vars are typically strings, not bytes-budgeted. This will confuse SDK users.

**[M4] `MoveTo` path length check vs. MOVE body part count is a footgun**
P0-2 §3.2 checks `drone.body` MOVE part count ≥ path length. But a drone with 2 MOVE parts and a path of length 10 gets `InsufficientMoveParts` — not immediately obvious. More importantly, the drone should be able to move step-by-step across multiple ticks; `MoveTo` seems to be a single-tick multi-step command, but this is never stated explicitly. If it's multi-tick, the validator semantics change entirely (fatigue accumulates between ticks).

**[M5] Resource `decay_rate` definition is inconsistent across documents**
DESIGN §3.1 defines `ResourceDef.decay_rate` as "每 tick 衰减比例 × 精度因子（0 = 不衰减）" — a fixed-point ratio. P0-7 world.toml example uses `decay_rate = 0.001` as a float literal (violating the no-float rule from DESIGN §8.8). The resource-decay mod in the mod marketplace also uses `decay_rate = 0.001`. This is a float masquerading as a config value — needs to be `decay_rate = 10` (× 10000 fixed precision) consistently.

**[M6] `MAX_DRONES_PER_PLAYER = 500` conflicts with empire-upkeep cost table**
DESIGN §8.7 shows "巨帝国（50 房, 500 drone）: 维护费 ≈ 3150/tick". If 500 drones is the hard cap (P0-2 §6), then "500 drone empire" is already the maximum. The table should show the hard cap as the ceiling example, but calling it "巨帝国" implies players might want more. This either means the cap needs to be higher or the examples should show costs at cap more explicitly.

**[M7] `swarm_simulate` semantics are underspecified**
P0-3 lists `swarm_simulate` as "offline simulation: given world snapshot, predict future N ticks." P0-9 classifies it as `Simulate` source with `snapshot-bound dry-run`. But there is no spec for: what N can be (max ticks), whether mod scripts execute, whether enemy AI runs or freezes, and what happens to the simulation result (is it cached? discarded?). This is a powerful competitive tool (predict enemy behavior) and its scope needs bounding.

---

### LOW

**[L1] Chapter numbering error in DESIGN.md**
Section 11 is titled "贡献指南" but subsection is labeled "10.2 代码规范" (should be 11.2). Minor but reflects document hasn't been proofread post-restructure.

**[L2] Arena fog-of-war default contradicts World default without explanation**
P0-7 §6 table shows `visibility.fog_of_war = false` for Arena. DESIGN §8.6 shows no Arena row for `fog_of_war`. P0-5 §7 states "Arena: 简化可见性: 比赛边界内全信息. 双方玩家看到整个竞技场. 公平竞技禁用 fog-of-war." This is fine, but the rationale (fairness) could be questioned — information asymmetry via fog-of-war *is* a skill expression. At minimum, this should be a configurable Arena parameter, not a hard default.

**[L3] `host_get_world_rules` appears in IDL but not in P0-4 host function whitelist**
P0-8 IDL §2 defines `get_world_rules` as a host function. P0-4 §3.2 whitelist shows `host_get_world_config` but not `host_get_world_rules`. P0-4 §8 cost table also omits it despite DESIGN §5.1 listing it. Minor inconsistency, but since this is a "single source of truth" IDL system, mismatches between P0-4 and P0-8 matter.

**[L4] Tutorial world tick interval (1s) vs. production (3s) is mentioned once and not enforced**
P0-6 §2.1 mentions "教程 tick 间隔 1s" but this is not reflected in P0-7 world.toml config schema (which only shows `tick_interval_ms`) or in P0-1 tick protocol. The tutorial world needs to be a first-class world mode configuration, not a footnote.

**[L5] Replay privacy `"world"` level is underspecified**
P0-5 §3.6 and DESIGN §10 define `replay_privacy` enum with value `"world"` meaning "同世界玩家可看." But what does "同世界玩家" mean exactly — current active players? Anyone who has ever played on that world instance? This edge case matters for persistent worlds with high player churn.

---

## Strengths

**[S1] Core design philosophy is exceptionally clear and maintained throughout**
"World only speaks WASM" is a strong, clean invariant. Every design decision traces back to it: MCP doesn't do game actions, the deferred command model, fuel metering over wall-clock — all coherent. This kind of philosophical clarity is rare in game design documents and makes the system easy to reason about and extend.

**[S2] The Command Source Model (P0-9) is unusually rigorous**
Explicitly modeling 12 instruction sources with capability matrices, audit requirements, and rate limits is work most game engines skip entirely and later regret. The distinction between `WASM` (gameplay), `MCP_Deploy` (meta), and `RuleMod` (economic-only) creates clean blast-radius boundaries for bugs and exploits.

**[S3] Determinism contract is production-grade**
Choosing Blake3 XOF as PRNG, banning `f64`, banning `std::HashMap` in favor of `Indexmap`, pinning Wasmtime to an exact version — these are decisions that show real understanding of determinism failure modes. Most game engines discover these problems after shipping. Doing it at Phase 0 is the right call.

**[S4] Anti-dominant-strategy economic design shows game design sophistication**
The progressive storage tax + local storage opacity + no-teleport transfer time is a coherent three-part system that addresses the "rich get richer" problem without banning accumulation. The stealth advantage of local storage (enemies can't see it) creates a genuine strategic tradeoff rather than just a penalty. This is the kind of emergent design that makes persistent worlds interesting.

**[S5] World Rules Engine scope is correctly bounded**
Using Rhai for server-mod scripts instead of WASM is the right call — the trust model is different (server owner vs. untrusted player), and removing floats from Rhai scripts maintains determinism without the overhead of process isolation. The `actions` API boundary (can deduct/award/emit, cannot call combat directly) is a sensible constraint that prevents mods from bypassing validation.

**[S6] Visibility policy is one of the strongest specs in the set**
The two-layer separation between "drone snapshot" (gameplay fairness) and "player view" (UX) is elegant and rarely done correctly. Making `is_visible_to()` a single canonical function called by every output surface — WASM snapshot, MCP, WebSocket delta, REST, replay — eliminates an entire class of information-leak bugs. The spectator visibility table is complete and thoughtful.

**[S7] The feedback loop (P0-6) is genuinely designed for learnability**
The LEARN → DECIDE → ACT → UNDERSTAND cycle is explicit and each quadrant has concrete tooling. The `swarm_explain_last_tick` output format (rejected commands with suggested fixes, notable events) is the kind of feature that separates a game from a framework. The "why is my drone idle?" debug output directly addresses the #1 Screeps frustration.

**[S8] World vs Arena split is clean and avoids the "one mode is an afterthought" trap**
Most games with two modes have one that's clearly bolted on. Here, the design explicitly distinguishes the emotional goals (creative persistence vs. competitive equality), the code lifecycle (hot-reload vs. locked), and the visibility defaults. The ranked league breakdown (Human/WASM, AI-assisted, AI tournament) acknowledges the unique player composition this game will attract.

---

## Summary

The design is ambitious, consistent, and shows real game design thinking beyond just systems architecture. The Phase 0 freeze is well-earned. The critical issues (C1–C3) are gaps in the game loop fundamentals that must be resolved before any player-facing Phase 1 milestone — they're not edge cases, they're the core of what players will be trying to do. High issues (H1–H6) are Phase 1 or Phase 2 blockers depending on which modes ship first. Medium issues are quality-of-life and consistency problems that will slow down SDK development and player onboarding if left to accumulate.

Recommended next step: write P0-10 covering drone lifecycle (age/death), Controller upgrade progression, and base body-part cost table as a single "game loop foundations" spec before Phase 1 implementation begins.
