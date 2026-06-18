# Swarm R-appcert-R2 — Economy Review (DeepSeek V4 Pro)

**Reviewer**: rev-dsv4-economy
**Direction**: Economy
**Date**: 2026-06-18

---

## Verdict: CONDITIONAL_APPROVE

The economic model is well-structured with strong anti-snowball mechanisms, flexible resource typing, and thoughtful maintenance curves. No Critical or High severity findings. Three Medium findings and five Low findings are identified — all addressable within the current design framework without fundamental rework.

---

## Strengths (亮点)

1. **Multi-tier resource architecture**: The global↔local storage separation with progressive tax, transport delay, and stealth advantage is a well-thought-out anti-hoarding design. Three configurable logistics modes (A/B/C) serve different player demographics without fragmenting the engine.

2. **Maintenance curves are properly superlinear**: Empire upkeep (O(n²) for rooms), progressive storage tax (up to 0.20%/tick at >85% capacity), and the controller repair hard cap (≤50% natural aging) create genuine diminishing returns. No "infinite growth by linear scaling" loophole identified.

3. **Anti-snowball is layered, not single-point**: Safe mode (500 tick) → soft launch (1500 tick PvE-only) → density-priority spawning → empire upkeep → storage tax → stealth advantage. Multiple independent mechanisms make coordinated exploitation infeasible.

4. **PoW economics are well-calibrated**: Default 24-bit difficulty (~150ms Rust, ~1.5s WASM, ~3s mobile) with server-authoritative challenge verification correctly balances anti-abuse against onboarding friction. The one-time consumption + 5-min TTL model is solid.

5. **Drone lifespan model creates natural churn**: Base 1500 tick lifespan with body-part age_modifiers (TOUGH +100, ATTACK -80) and active_aging at 110% creates meaningful trade-offs between combat power and longevity. The controller repair hard cap prevents indefinite drone preservation.

6. **Account deletion asset handling is complete**: Three disposition modes (abandon/recycle/transfer) with Ed25519-signed transfer acceptance, 30-day grace period, and clear state machine semantics.

7. **No hardcoded resource types**: The engine operates on `HashMap<ResourceName, Amount>` with all resource types defined in world.toml — genuinely extensible without requiring engine changes.

---

## Findings

### Medium Severity

#### M1: Market/Trading economy is referenced but undefined

**Files**: gameplay.md (resource storage model, Terminal), 07-world-rules.md (market_requires_terminal)

The design references `Terminal` building for market trading, `market_requires_terminal` configuration, and `tradeable` resource flags — but there is **no market design spec**. Critical questions unanswered:
- Price discovery mechanism (order book? fixed exchange? auction?)
- Market maker / liquidity model
- Cross-room trade settlement (does Terminal need logistics connection?)
- Market manipulation prevention
- Whether market orders consume tick actions or are async

The `market_requires_terminal` config implies a building requirement, but without a spec, this is a placeholder that could introduce economy-breaking dynamics when implemented.

**Recommendation**: Either (a) add a market spec before Phase 1 implementation, or (b) explicitly mark market/trading as Phase 2+ and remove Terminal from the Phase 1 building list to avoid shipping an incomplete economic subsystem.

---

#### M2: In-transit resource handling during account deletion is undefined

**Files**: auth.md §13, commands.md (TransferToGlobal/TransferFromGlobal)

When a player deletes their account (auth.md §13.1), resources in transit (`transfer_to_global_time` default 10 tick, `transfer_from_global_time` default 5 tick) have ambiguous fate:
- Resources already deducted from local storage but not yet credited to global (or vice versa) are in a limbo state
- The design says in-transit resources "can be intercepted by enemy patrol drones" during PvP, but there's no handler for owner deletion mid-transit
- If transfer acceptance/refund semantics depend on the source player existing, account deletion could permanently orphan resources

**Recommendation**: Add a clause in auth.md §13.1: on account deletion, all in-transit resources are (a) forfeited (simplest), (b) auto-completed to destination, or (c) refunded to source. Document the choice and ensure the cargo_in_transit_system handles the deleted-player edge case.

---

#### M3: No explicit fuel↔resource economic equilibrium analysis

**Files**: engine.md §3.2, tech-choices.md §2, gameplay.md §8.5

The fuel metering system (WASM instruction counting via Wasmtime) charges players per tick. However, the relationship between fuel cost and resource generation is not analyzed:
- A player with a perfectly efficient algorithm can generate resources at some rate R per tick
- Fuel consumption is per-instruction, independent of the economic value generated
- The design has Overload as a counter (reduces target's fuel by 500k), but this is a tactical PvP tool, not an economic equilibrium mechanism
- Without analysis, an "algorithmic snowball" is possible: a player who discovers a near-optimal strategy could outgrow all constraints faster than maintenance curves can check them

The progressive storage tax and empire upkeep address **resource** snowballing, but the **computation→resource** pipeline lacks economic validation.

**Recommendation**: Add a brief economic analysis section (perhaps in a new spec or gameplay appendix) establishing the expected fuel-to-resource conversion rate under optimal play, and confirming that maintenance curves dominate at all resource levels. This doesn't need to be a full simulation — a bounding analysis is sufficient.

---

### Low Severity

#### L1: Certificate renewal has zero recurring economic cost

After the one-time registration PoW, certificate renewal (`swarm_renew_certificate`) requires only proof of private key possession — no ongoing PoW, resource cost, or computational burden. In a persistent world spanning millions of ticks, this means a ~150ms Rust PoW investment buys perpetual access.

While not a direct exploit vector, this creates an asymmetry where the registration barrier decays to zero over time. A world that runs for 100,000 ticks effectively grants free access to anyone who solved PoW once.

**Recommendation**: Consider making certificate renewal require a lightweight re-PoW (e.g., 16-bit difficulty, ~65K attempts) or a small in-game resource cost configurable via world.toml. Alternatively, document that this is an accepted design choice (one-time gate, not recurring toll).

---

#### L2: Recycle 50% refund may create economic arbitrage with age_modifiers

**Files**: gameplay.md §8.2 (Drone lifecycle, Recycle)

The Recycle command refunds 50% of spawn cost. Combined with body part age_modifiers:
- A drone with TOUGH parts (+100 age each) that is recycled at age 1400/1600 effectively returns 50% resources for a drone that was 87.5% through its lifespan
- The remaining 12.5% lifespan is lost, but the 50% refund on the full body cost creates a potential "recycle at the last moment" strategy
- Active_aging at 110% partially mitigates this but doesn't eliminate the arbitrage

The Tutorial world's 100% refund is explicitly for learning, but the standard 50% refund hasn't been validated against optimal play patterns.

**Recommendation**: Consider making the recycle refund proportional to remaining lifespan ratio (e.g., `refund = base_refund × (lifespan_remaining / lifespan_max)`). This eliminates the last-moment-recycle arbitrage while still rewarding early strategic pivots.

---

#### L3: No global resource sink in persistent World mode

In a persistent world with continuous resource source regeneration, resources accumulate indefinitely. The design provides several sinks:
- Drone spawn costs (one-time, per drone)
- Building costs (one-time, per building)
- Empire upkeep (per tick, capped by player's willingness to expand)
- Progressive storage tax (per tick, only on global storage)
- Resource decay mod (per tick, configurable)

However, empire upkeep is player-scoped and can be avoided by staying small. The progressive tax only applies to global storage — a player hoarding in local storage pays zero. Over long timescales (months/years), the total resource pool grows unboundedly.

The `max_pve_output_per_tick` constraint (§9.0 in modes.md) caps NPC-generated resources, but doesn't address player-generated resources.

**Recommendation**: Either (a) add a world-level resource sink (e.g., global maintenance decay on all stored resources at a very low rate, configurable via world.toml), or (b) explicitly document that persistent-world inflation is an accepted dynamic and provide administrative tools for server operators to manage it (resource wipes, seasonal resets, etc.).

---

#### L4: AI agent PoW onboarding cost is higher than the timing estimates suggest

**Files**: auth.md §9.2, auth.md §4.2

The PoW difficulty table estimates ~150ms for Rust native, ~1.5s for WASM, ~3s for mobile. However, many AI agents (LLM-based) operate through MCP tool calls — they don't have native blake3 implementations in their runtime. The AI agent must either:
1. Shell out to a native binary for PoW solving (adds process spawn overhead)
2. Implement blake3 in their runtime language (Python ~800ms, but many agents use JS/TS in Node which is WASM ~1.5s)
3. Use a pre-solved PoW pool (not addressed in the design)

The design says "AI agent must be capable of solving PoW locally" but doesn't provide guidance for agents that don't have efficient blake3 access.

**Recommendation**: Add an `auth/onboarding-ai` document section covering PoW solving strategies for AI agents, including recommended blake3 libraries per runtime and whether pre-solved PoW pools are permitted by server policy.

---

#### L5: Controller repair hard cap wording has arithmetic ambiguity

**Files**: gameplay.md §8.2 (Drone lifecycle)

The paragraph states:
> "每 tick 总 age 回退不超过自然增长（+1/tick）的 50%（即 max(0, age + 1 - min(0.5, controller_count * 0.5))）"

The formula `max(0, age + 1 - min(0.5, controller_count * 0.5))` is ambiguous:
- It appears to mix age (current drone age in ticks) with a rate limiter (max rollback per tick)
- The `min(0.5, controller_count * 0.5)` term caps at 0.5 regardless of controller count, making additional controllers useless beyond 1
- The intended meaning is likely: "max age reduction per tick = 0.5 ticks" (i.e., at most half of natural aging can be reversed), which makes `controller_count` irrelevant at any value ≥1

If the intent is truly "one controller is enough, additional controllers add zero benefit," this should be stated explicitly. If the intent is "each controller adds 0.5 but capped at 0.5 total," the formula is correct but the text is misleading.

**Recommendation**: Rewrite as: "Per tick, total age reduction across all controllers is capped at 0.5 ticks (50% of natural aging). Owning multiple controllers does not increase this cap." This eliminates confusion about `controller_count * 0.5`.

---

## Consistency Gaps

| Gap | Documents | Issue |
|-----|-----------|-------|
| Global storage tax tiers | gameplay.md §8.2 shows `[(30,0),(60,1),(85,5),(100,20)]` but 07-world-rules.md doesn't include the tax tier config | Tax tiers are described in gameplay but not surfaced in the world.toml config schema |
| `transfer_to_global_time` minimum | gameplay.md §8.2 says "不可为 0" (cannot be 0), but 07-world-rules.md doesn't include this constraint in the schema | Validation rule exists in prose but not in config schema |
| Market references across docs | gameplay.md, modes.md, interface.md all reference market/trading, but no market spec exists | Cross-document consistency gap (see M1) |

---

## Algorithmic Risks

1. **Empire upkeep O(n²) for rooms**: The superlinear room cost creates a hard expansion ceiling. For 50 rooms with `room_superlinear=2` (0.0002 fixed-point), per-room cost grows to ~0.5 extra per room — this is a soft ceiling, not a hard one. The design's "not insurmountable" claim holds at default values but needs tuning guidance for server operators.

2. **Seed shuffle for command ordering**: The seeded shuffle using Blake3(tick || world_seed) provides both determinism and fairness. However, the seed rotation interval (10,000 ticks) and the accepted risk of forward-secrecy compromise are well-documented (01-tick-protocol.md §3.1). No algorithmic concern — this is a security risk that lives in the security reviewer's domain.

3. **Fuel metering determinism**: Wasmtime fuel metering is deterministic per the Wasmtime spec. The fuel→economic value pipeline is not analyzed (see M3), but the metering mechanism itself is not at fault.

---

## Summary

The economic design is robust at the structural level: resource types are extensible, maintenance curves are genuinely superlinear, anti-snowball is multi-layered, and the global↔local storage model creates meaningful strategic depth. The three Medium findings (missing market spec, in-transit resource handling on account deletion, unvalidated fuel↔resource equilibrium) are all addressable within the current design without requiring architectural changes. The five Low findings are polish-level improvements.

**Condition**: Address M1 (market spec or deferral), M2 (in-transit resource handling), and M3 (fuel↔resource equilibrium analysis) before entering Phase 1 implementation.
