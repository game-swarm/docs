# Architect Review — Algorithmic Correctness (Round 2)

**Reviewer**: DeepSeek V4 Pro | **Verdict**: APPROVE_WITH_RESERVATIONS

## Phase 2 Blockers
1. CG1/DA7 — FDB commit timing contradiction between DESIGN.md and P0-1 (doc fix)
2. DA13 — Sandbox fork overhead (prototype process pool vs fork/kill)
3. DA5 — EXECUTE 500ms feasibility (prototype with 50K commands)

## Key Findings (20 Concerns + 5 Consistency Gaps + 5 Algorithmic Risks)

### Critical
- **DA7/CG1**: FDB committed in EXECUTE per DESIGN.md+P0-1 §3.4, but also in BROADCAST per P0-1 §4.2 → contradiction. Unify to EXECUTE.
- **DA13**: Fork/kill per tick = 167 forks/sec for 500 players. Consider process pool.
- **DA5**: Serial EXECUTE with 50K commands may exceed 500ms. Prototype required.
- **DA3**: world_seed leak via replay or statistical observation. Rotate seed periodically.

### High
- **DA2**: Seeded shuffle fairness bias — players with more commands have earlier expected first-command position
- **DA4**: Cross-shard tick synchronization undefined
- **DA12**: FDB 10MB transaction limit may be hit at scale

### Medium
- **DA6**: Tick abandonment behavior undefined (tick_counter, fuel refund)
- **DA9**: NATS failure recovery protocol incomplete (gateway ack needed)
- **DA11**: PRNG algorithm not specified (use ChaCha12, not std::hash)
- **AR3**: Seeded shuffle hash must be fixed algorithm (blake3), not std::hash
- **AR5**: FDB vs Bevy ECS dual state source needs verification after recovery
- **DA18**: Full replay validation too slow for CI — use sampling + checksum

### Documentation
- 20 numbered concerns (DA1-DA20), 5 consistency gaps (CG1-CG5), 5 algorithmic risks (AR1-AR5)
- See full process log for complete text
