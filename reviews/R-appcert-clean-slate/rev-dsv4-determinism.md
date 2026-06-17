# Review Report — Determinism (DeepSeek V4 Pro)

**Reviewer**: rev-dsv4-determinism (Architect Reviewer)
**Date**: 2026-06-17
**Review scope**: Clean-slate full review of Swarm docs post application-layer certificate redesign
**Document set**: design/{README, auth, interface, engine, tech-choices}.md + specs/{01-tick-protocol, 02-command-validation, 04-wasm-sandbox, 07-world-rules, 12-gateway-protocol}.md + specs/security/{03-mcp-security, 09-command-source}.md + specs/reference/mcp-tools.md + GETTING-STARTED.md + RUNBOOK.md

---

## Verdict: CONDITIONAL_APPROVE

The determinism architecture is sound in its core design — the seeded shuffle, ECS chain ordering, Blake3 XOF PRNG, deferred command model, and FDB atomic commit form a coherent deterministic foundation. However, two issues reach the threshold where clarification is needed before Phase 1 implementation: (1) the epoch-bump / deployed-module semantic gap, and (2) the wall-clock timeout's impact on replay determinism. Neither is a design flaw per se, but both are ambiguous enough to cause divergence in implementation. Recommended: resolve the two High-severity questions below, then proceed.

---

## Strengths

1. **Core determinism stack is well-specified**: Blake3 XOF as PRNG (§tech-choices §8), `seeded_shuffle` for player ordering (§01-tick-protocol §3.1), `.chain()` ECS ordering (§engine §3.4), deferred command model (§04-wasm-sandbox §3) — each layer has a clear spec and explicit determinism contract.

2. **Snapshot truncation determinism is explicit**: §01-tick-protocol §2.3 defines the sorting key `(bucket, distance_to_drone, entity_id)` and explicitly states it's fully determined by world state — no wall-clock, no RNG, no parallelism. This is the right level of precision.

3. **Code-signing certificate expiry semantics are clear and consistent**: auth.md §5.4, specs/security/09 §3.4, and specs/security/03 §1.1 all agree: "证书自然过期不影响已部署模块继续运行。" This is a strong contract — the deployed module's lifecycle is decoupled from the signing certificate's validity window. Cross-document consistency verified.

4. **Cross-server federation identity mapping is deterministic**: auth.md §15.2 and §7.1 define `player_id_local = blake3("federated:" + remote_server_id + ":" + remote_player_id) → u64`. The mapping is reproducible and isolated per world — no shared state, no cross-world contamination. Collision probability documented.

5. **FDB rollback + Bevy World snapshot restoration is specified**: §01-tick-protocol §3.5 defines the snapshot capture scope (both Resources and Components) and the restore path. The COLLECT-result caching (§3.5 COLLECT 结果跨重试缓存) is a practical optimization that avoids re-executing WASM on retry.

6. **WASM sandbox bans all non-deterministic syscalls**: §04-wasm-sandbox §9.1 explicitly denies `clock_gettime`, `getrandom`, `fork`, `socket` — all vector for non-determinism. The "relaxed mode" (§9.5) is gated behind `world.mode == "development"` and engine refuses to start in production with it enabled.

---

## Findings

### Finding D1: Epoch bump vs. deployed module lifecycle is ambiguous (HIGH)

**Category**: doc inconsistency / security gap
**Evidence**: 
- specs/security/09-command-source.md §3.4: "Auth Service epoch：全局单调递增整数。emergency bump 后所有旧 epoch 证书立即失效，强制全量重新认证"
- auth.md §5.4: "证书自然过期不影响已部署模块继续运行"
- specs/security/03-mcp-security.md §1.1: "部署成功后 module_hash 进入世界状态；证书自然过期不影响已部署模块继续运行"
- specs/security/09-command-source.md §3.4: "证书吊销是安全事件，服务器按 revocation reason 冻结、回滚或继续允许既有模块"

**Analysis**: The "expired cert → module continues running" contract is clear for natural expiry. But an epoch bump is NOT natural expiry — it's a mass invalidation of all certificates. What happens to already-deployed modules signed by old-epoch certificates? Three interpretations exist:

a) Epoch bump = mass revocation → all modules signed by old-epoch certs are "revoked" → the revocation policy (freeze/rollback/continue) applies per module.
b) Epoch bump invalidates certs but modules were already accepted → they continue running (like natural expiry).
c) Epoch bump is a special case distinct from both expiry and revocation — the spec doesn't define its effect on deployed modules.

**Impact**: An operator performing an epoch bump (e.g., after Server Intermediate CA compromise) would not know whether deployed modules continue running or get frozen/rolled back. This is an operational safety issue — the wrong interpretation could either (a) leave attacker-deployed modules running after a CA compromise, or (b) disrupt all players' strategies unnecessarily.

**Recommendation**: Add an explicit row to the cert lifecycle table (auth.md §5.4 or specs/security/09 §3.4) that defines:
```
| Epoch bump | 所有旧 epoch 证书立即失效 | 已部署模块按 revocation reason 处理：<default policy> |
```
The default policy for epoch bump should be specified (suggest: pausable, reviewable, not automatic freeze).

---

### Finding D2: Wall-clock timeout creates replay non-determinism (HIGH)

**Category**: security gap / design concern
**Evidence**:
- specs/core/01-tick-protocol.md §2.2: `collect_timeout_ms = 2500 // 硬截止时间`
- specs/core/04-wasm-sandbox.md §6: "执行时间（墙钟）| 2500 ms | Epoch interruption"
- specs/core/04-wasm-sandbox.md §6: "Fuel（CPU 指令）| 10,000,000 | Wasmtime fuel metering"
- design/engine.md §3.3: "确定性需要：... 所有随机数来自确定种子 PRNG"

**Analysis**: The WASM execution has TWO independent limits — fuel (10M instructions, deterministic) AND wall-clock (2500ms, hardware-dependent). If a WASM module is close to the edge:

- On fast hardware: fuel limit hits first → deterministic cutoff → same output every time.
- On slow hardware: wall-clock hits first → timeout → empty command list → different world state.

This means the same tick, same snapshot, same WASM code, same seed can produce DIFFERENT world states when replayed on different hardware. The determinism contract (§engine §3.3): "相同初始状态 + 相同玩家指令 → 相同世界状态" breaks if "相同玩家指令" depends on which limit fires first.

**Defense analysis**: The fuel limit (10M) is the primary constraint and wall-clock (2500ms) is the safety net. In practice, 10M WASM instructions should complete well under 2500ms on any modern CPU. But:
- Wasmtime's Cranelift JIT compilation quality varies by `target_arch` (§security/09 §3.5)
- The spec doesn't guarantee that 10M fuel always completes within 2500ms
- Replay on a different architecture (e.g., x86_64 → aarch64) could hit different performance profiles

**Recommendation**: Add a statement in §01-tick-protocol §2.2 or §engine §3.3 that:
1. Wall-clock timeout is a safety net, NOT a determinism boundary — fuel metering is the authoritative limit.
2. TickTrace records WHICH limit fired (fuel_exhausted vs wall_clock_timeout) so replays can validate consistency.
3. On replay: if the original tick was fuel-exhausted, replay must reproduce the same fuel-exhausted cutoff; if wall-clock timeout, flag as non-reproducible (or re-execute without wall-clock limit in replay mode).

---

### Finding D3: world_seed forward secrecy — acknowledged risk (MEDIUM)

**Category**: security gap (documented, accepted)
**Evidence**: specs/core/01-tick-protocol.md §3.1, "前向保密威胁模型" section

**Analysis**: `new_seed = Blake3(old_seed || current_tick)` is NOT forward-secure — knowing the current seed reveals all future seeds. The document itself provides an excellent threat model analysis and correctly identifies:
- Impact: future tick ordering and RNG become predictable
- Mitigation: periodic rotation (10K tick), operator epoch bump
- Design decision: "不实现密码学完善前向保密" because external entropy injection breaks determinism

This is well-documented and the trade-off is articulated clearly. No action required — this is a strength in documentation quality.

**Note**: The seed rotation interval (default 10,000 ticks = ~8.3 hours at 3s/tick) defines the blast radius. Consider documenting this time-equivalent in the spec for operator awareness.

---

### Finding D4: Cross-server federated identity collision window (MEDIUM)

**Category**: doc inconsistency
**Evidence**: 
- auth.md §7.1: for 10^6 users, collision probability is ~2.7×10^-8 for local namespace
- auth.md §15.2: federated namespace uses `blake3("federated:" + remote_server_id + ":" + remote_player_id) → u64`

**Analysis**: The collision probability for federated identities is independent per world. If World B has N federated identities from World A, each mapped via a different hash, the collision probability is ~N²/(2×2^64). This is fine in isolation. But there's a subtlety: what happens if two different remote players map to the same local player_id? auth.md §7.1 says "注册时检测 FDB auth/identities/ 唯一索引冲突，返回 username_taken" — but the federated path (§15.4) maps remote_player_id → local_player_id in a different namespace. The `swarm_federated_login` flow doesn't mention collision detection.

**Recommendation**: Add a collision check in the federated_login flow (§15.2, step 5-6): if the derived player_id already exists and belongs to a DIFFERENT remote identity, reject with `identity_conflict`. This is already an error code in the error table (§10.6).

---

### Finding D5: Relaxed-mode clock_gettime override value unspecified (MEDIUM)

**Category**: doc inconsistency / security gap
**Evidence**: specs/core/04-wasm-sandbox.md §9.5: "clock_gettime | 禁止 | 允许（确定性种子） | 无——引擎仍覆盖返回值"

**Analysis**: The "relaxed mode" allows `clock_gettime` for dev/debug worlds. The spec says "引擎仍覆盖返回值" (engine overrides return value) but doesn't specify what value is returned. For the dev world to be useful for testing determinism, the overridden value must be deterministic (e.g., fixed to tick_start_time, or derived from world_seed + tick_number). If it returns host wall-clock time, WASM code could observe non-deterministic behavior even in relaxed mode.

**Recommendation**: Specify the overridden value in §04-wasm-sandbox §9.5: `clock_gettime` returns `tick_start_time` (a fixed timestamp set at the start of the tick, derived from the world seed). This makes dev-mode behavior deterministic.

---

### Finding D6: Deploy nonce IP-binding creates cross-environment replay barrier (LOW)

**Category**: deferred implementation concern
**Evidence**: specs/security/09-command-source.md §7.3: "IP-bound（默认）: 签发 IP 与请求 IP 一致才接受"

**Analysis**: The deploy nonce is IP-bound by default. This means a deploy event recorded in TickTrace has an implicit dependency on the network topology. During replay, the nonce validation step would need to either skip IP binding (replay mode) or the replay environment must match the original IP. This isn't a determinism issue for game state (deploy is out-of-band from tick), but it affects the reproducibility of the FULL tick record including deploy events.

**Recommendation**: Document replay-mode behavior for IP-bound nonces in the replay spec (or add a note to §7.3).

---

### Finding D7: host_path_find cost cache_miss_penalty semantics unclear (LOW)

**Category**: doc inconsistency
**Evidence**: specs/core/04-wasm-sandbox.md §8: "host_path_find | 500 × explored_nodes + 200 × expanded_edges + cache_miss_penalty"

**Analysis**: The cost formula includes `cache_miss_penalty` but the cache key is `(from, to, terrain_hash, player_visibility_fingerprint)`. Since the sandbox process is "per tick fork → execute → kill" (§04 §1), there is no cross-tick cache. The cache must be in-process, meaning within a single tick's execution, repeated path_find calls for the same origin-destination pair could hit a cache. This is deterministic (same code, same queries, same cache hits). But the `cache_miss_penalty` value isn't quantified — is it a fixed offset or proportional to something?

**Recommendation**: Quantify `cache_miss_penalty` as a fixed value (e.g., +5000 fuel) or state that it's absorbed into `explored_nodes` (i.e., first query incurs computation cost; cached queries skip it).

---

### Finding D8: DOCS: seed_rotation_interval time-equivalent not documented (LOW)

**Category**: doc inconsistency
**Evidence**: specs/core/01-tick-protocol.md §3.1: `seed_rotation_interval = 10000`

**Analysis**: The rotation interval is specified as 10,000 ticks. At 3s/tick, this is ~8.3 hours. Documenting the time-equivalent helps operators reason about the blast radius of a seed leak. Minor.

---

## Questions / Assumptions

1. **Assumption**: The fuel metering is the authoritative determinism boundary, and wall-clock timeout fires only in pathological cases. Is there a measured ratio of 10M fuel to wall-clock time on target hardware (e.g., x86_64, 2+ GHz)?

2. **Assumption**: `clock_gettime` in relaxed mode returns a deterministic value derived from the tick, not host time. Confirmed?

3. **Question**: In the federation flow (§auth §15.2), step 3 says "客户端用 World A 证书对应私钥签名 World B 的 federation challenge" — is this challenge deterministic (derived from World B's seed) or random per-request? If random per-request, it doesn't affect game determinism (federation login is out-of-band).

4. **Question**: The `deploy_nonce` in §security/09 §7.3 has `IP-bound（默认）` — is there a config to disable IP binding for replay/debug environments? If deploy events need to be reproducible in replay, IP binding creates a dependency on network state.

---

## Consistency Gaps (cross-document)

| Gap | Docs involved | Issue |
|-----|---------------|-------|
| Epoch bump → deployed modules | auth.md §5.4 vs specs/security/09 §3.4 | Unclear whether epoch bump triggers revocation policy on deployed modules |
| CRL retention window | auth.md §5.5 vs specs/security/09 §3.4 | Both define the CRL window but auth.md says `max_certificate_ttl + max_clock_skew + federation_revocation_cache_ttl + operational_grace` while specs/security/09 says the same — consistent |
| WASM timeout behavior | specs/core/01 §2.2 vs specs/core/04 §6 | Both mention 2500ms wall-clock + 10M fuel — consistent |
| Deploy payload signed fields | auth.md §5.4 vs specs/security/09 §3.2 | auth.md says `module_hash + metadata` but specs/security/09 specifies full DeployPayload with 9 fields including nonce, version_tag, etc. — specs/security/09 is more complete and should be referenced from auth.md |

---

## Algorithmic Review

- **blake3→u64 collision**: For N players, P(collision) ≈ N²/(2×2^65). At 10^6 players: ~2.7×10^-8. At 10^7: ~2.7×10^-6. Acceptable; collision detection at registration mitigates tail risk.

- **Seeded shuffle**: Fisher-Yates with Blake3 XOF. Deterministic given `(tick_number, world_seed, active_player_set)`. Correct.

- **Snapshot truncation**: Bucket-based priority with deterministic sort key `(distance, entity_id)`. The `distance_to_drone` changes as drones move — this is correct since the snapshot freezes at collection start.

- **ECS chain ordering**: `.chain()` guarantees sequential execution. The parallel systems (`regeneration`, `decay`) are proven data-independent (read/write matrix in §01 §3.4). Proof is sound.

---

## Summary

The determinism architecture is well-designed and mostly well-documented. The two HIGH findings (epoch bump semantics, wall-clock replay) are clarifications, not redesigns — they can be resolved with small doc additions. No blockers to Phase 1 implementation, provided D1 and D2 are addressed.

**Reviewer confidence**: High — all referenced documents were read in full; cross-references verified; algorithmic claims checked.
