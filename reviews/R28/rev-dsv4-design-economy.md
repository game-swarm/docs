# R28 Closure Verification — rev-dsv4-design-economy

## Verdict: CONDITIONAL_APPROVE

All 4 Design/Economy items from R27 verified CLOSED. No GAPs found.

## Items Verified

### D-H2: swarm_get_objectives API

**Status: CLOSED**

Evidence:

- `specs/reference/api-registry.md:244` — `swarm_get_objectives` registered as MCP tool with full schema: `{player_id?, scope?} → {objectives: [{id, type, description, required, current, reward, priority, expires_at?}]}`, rate limit 5/tick, scope `swarm:read`, replay class `read_replay_safe`, visibility filter `owner`
- `specs/reference/game_api.idl.yaml:56-67` — `ObjectiveType` enum defined with 8 variants: collect_resource(0), build_structure(1), claim_room(2), spawn_drones(3), deploy_code(4), survive_ticks(5), defeat_enemy(6), event(7)
- `specs/reference/game_api.idl.yaml:657-700` — `swarm_get_objectives` endpoint with complete input/output schema, player_id/scope params, nested object structure for required/current/reward
- MCP tool count: 57 (matches commit statement "Onboarding 11, total 57")

Machine-readable contract is complete. AI agents can query objectives by type, check current progress vs required, and plan accordingly. The 8 ObjectiveType variants cover all core game loops (resource, build, claim, spawn, deploy, survive, PvP, event).

### E-H1: Allied Transfer 拦截完整规则

**Status: CLOSED**

Evidence:

- `specs/core/09-snapshot-contract.md:214-252` — §3.2a "运输中拦截" with complete design:
  - **Intercept window**: last 50 of 200 tick delay (tick 150-200), first 150 tick safe
  - **Intercept conditions**: attacker drone position (receiver room, same-tile or range=1), PvP=enabled, non-ally, CARRY(Steal) or ATTACK(Destroy) parts, per-transfer cooldown, visibility required
  - **Intercept results**: Steal (50% to attacker, 50% to receiver) vs Destroy (100% destroyed)
  - **Success formula**: `clamp(60% + min(extra_parts × 5%, 25%) - (has_escort ? 30% : 0%), 10%, 85%)`
  - **Escort defense**: receiver drone with ATTACK parts on same tile auto-escorts (no extra command cost)
  - **Determinism**: Blake3("intercept" || transfer_id || tick || world_seed), result in TickTrace
  - **Notification**: All 3 parties receive AlliedTransferIntercepted/InterceptFailed event
  - **Audit**: (transfer_id, attacker_player_id, attacker_drone_id, mode, success, resources_affected, tick)

Closed as "最终设计" (final design), not MVP placeholder. Complete logistics warfare deferred to Rhai mods — correct per R27 scope.

### ML-6: World Tiers Taxonomy

**Status: CLOSED**

Evidence:

- `design/economy-balance-sheet.md:119-138` — §3 "模式差异" table: Tutorial | Vanilla (Novice) | Standard tiers with differentiated base_upkeep (10/30/50), room_soft_cap (20/15/10), transfer lock, PvE cap, storage tax, safe_mode_duration, starting_resources, free_upkeep parameters. Each tier has a distinct product role (Tutorial=learning, Novice=gentle, Standard=full anti-snowball).
- `design/gameplay.md:530` — Special attack tiering: Leech/Fabricate as Tier 2, Tutorial/Novice disable all special attacks, Standard+ enables all 8
- `design/gameplay.md:777-782` — §9 table: Tutorial (全禁用), Novice (全禁用), Standard (全部 8 种可用), with `world.toml` override for server owners

The original R27 definition called for "Tutorial/Novice/Standard/Advanced/Modded" (5 tiers). The fix settled on 3 primary tiers with "Standard+" and modded capability handled through world.toml configuration + Rhai mod system rather than an explicit "Advanced"/"Modded" tier label. This is an acceptable simplification — "Standard" with configurable parameters covers the Advanced use case, and Rhai modding covers the Modded use case. The taxonomy is product-complete for MVP.

### ML-7: Replay Privacy / Code Disclosure

**Status: CLOSED**

Evidence:

- `design/gameplay.md:1261` — `replay_with_source` field: default `false` — "默认 replay 不含源码: 回放只包含指令序列和状态变更，不包含 WASM 模块源码或 source map"
- Players opt-in via `replay_with_source = true` (requires world config to allow; server owner may forbid)
- Public worlds: server owner can force `replay_with_source = true` for full transparency
- Source map / code line provenance: requires compile-time embedding of debug symbol section (opt-in)
- `design/gameplay.md:1259` — `replay_privacy` enum (private/allies/world/public) provides visibility control; Arena post-match forces `public`
- `specs/security/05-visibility.md:139,323` — replay_privacy filter enforces visibility constraints on spectators

All 3 requirements satisfied: (1) default replay without source ✓, (2) source map opt-in via compiler flag ✓, (3) code line provenance opt-in via debug symbols ✓.

## Summary

```
Item    | Status  | Evidence Location
--------|---------|------------------
D-H2    | CLOSED  | api-registry.md:244 + game_api.idl.yaml:56-67,657-700
E-H1    | CLOSED  | 09-snapshot-contract.md:214-252
ML-6    | CLOSED  | economy-balance-sheet.md:119-138 + gameplay.md:530,777-782
ML-7    | CLOSED  | gameplay.md:1259-1261 + security/05-visibility.md:139,323
```

## Scope Notes

- Items outside Design/Economy domain (B1-B5, D1-D6, other H/ML items): N/A per review scope
- E-H1 intercept rules properly defer full logistics warfare to Rhai mods — correct scope boundary
- ML-6 simplified to 3 primary tiers with Standard+ and modded as implicit — acceptable for MVP product taxonomy