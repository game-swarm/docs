# R-appcert-clean-slate — Speaker Verdict

## Overall verdict

**REQUEST_MAJOR_CHANGES**

14/14 reviewer artifacts are present and were included in this synthesis. The application-certificate redesign is broadly endorsed as the right architectural direction: no reviewer recommends abandoning Server CA + CSR + purpose-isolated application certificates + canonical request signatures. However, the current documentation is not implementation-ready. Two independent reviewers returned `REQUEST_MAJOR_CHANGES` (`rev-dsv4-apidx`, `rev-dsv4-performance`), and the remaining 12 returned `CONDITIONAL_APPROVE` rather than clean approval.

The consensus is: keep the design, but do not enter implementation until the public API/auth contract and request-path performance contract are closed.

## Reviewer matrix — 14/14 completeness

| Direction | GPT-5.5 reviewer | Verdict | DeepSeek V4 Pro reviewer | Verdict | Artifact status |
|---|---:|---|---:|---|---|
| Architect | rev-gpt-architect | CONDITIONAL_APPROVE | rev-dsv4-architect | CONDITIONAL_APPROVE | 2/2 present |
| Security | rev-gpt-security | CONDITIONAL_APPROVE | rev-dsv4-security | CONDITIONAL_APPROVE | 2/2 present |
| Designer | rev-gpt-designer | CONDITIONAL_APPROVE | rev-dsv4-designer | CONDITIONAL_APPROVE | 2/2 present |
| Performance | rev-gpt-performance | CONDITIONAL_APPROVE | rev-dsv4-performance | REQUEST_MAJOR_CHANGES | 2/2 present |
| Economy | rev-gpt-economy | CONDITIONAL_APPROVE | rev-dsv4-economy | CONDITIONAL_APPROVE | 2/2 present |
| API/DX | rev-gpt-apidx | CONDITIONAL_APPROVE | rev-dsv4-apidx | REQUEST_MAJOR_CHANGES | 2/2 present |
| Determinism | rev-gpt-determinism | CONDITIONAL_APPROVE | rev-dsv4-determinism | CONDITIONAL_APPROVE | 2/2 present |

Completeness note: parent task `t_c4eb492c` had no kanban result recorded, but `/data/swarm/docs/reviews/R-appcert-clean-slate/rev-dsv4-designer.md` exists, is non-empty, and was included as the authoritative reviewer artifact.

## Consensus strengths

1. **Core auth direction is accepted.** All directions that discuss the trust model consider Server CA + CSR + application-layer certificates directionally sound.
2. **Purpose isolation is a strong property.** Reviewers repeatedly praised separate Device / CodeSigning / Admin / Session usage semantics.
3. **AI/human fairness is preserved.** MCP remains management/deploy surface; AI agents deploy WASM rather than bypassing gameplay via a privileged executor.
4. **Recovery model is richer than OAuth/JWT baseline.** Email, passkey, admin, and agent-proxy/handoff flows give the design a credible offline/self-hosted story.
5. **Certificate expiry not bricking deployed modules is important.** Economy and performance reviewers both identified this as a major positive for autonomous agents.
6. **The problems are mostly contract closure, not conceptual rejection.** The dominant issue class is cross-document/API ambiguity and missing implementation contracts.

## Consensus blockers / high-priority findings

### B1 — Public MCP/auth contract is internally inconsistent and incomplete

**Consensus strength:** Very high. Raised across Architect, Security, Designer, Performance, Economy, API/DX, and Determinism; both GPT and DeepSeek reviewers found variants.

**Representative reviewers:**
- `rev-gpt-architect`: Gateway MCP auth still says JWT; `swarm_deploy_challenge` absent; audience formats inconsistent.
- `rev-dsv4-architect`: Critical C1 audience incompatibility; Critical C2 Gateway JWT dual-track; High H1 missing `swarm_deploy_challenge`; High H3 DeployPayload mismatch.
- `rev-gpt-security`: High JWT/app-cert conflict; High Blake3 MAC vs Ed25519 signing conflict.
- `rev-gpt-designer`: High AI onboarding not executable; High deploy nonce missing from public MCP tables.
- `rev-dsv4-designer`: High compressed onboarding; missing onboarding/auth resources; deploy API mismatch.
- `rev-gpt-performance`: High deploy nonce API missing; compile-time nonce fallback lacks public contract.
- `rev-gpt-economy`: High Gateway JWT residue; High deploy nonce missing; Getting Started path misaligned.
- `rev-gpt-apidx`: High JWT auth drift; High deploy payload examples disagree; High MCP inventory drift.
- `rev-dsv4-apidx`: Critical `swarm_deploy_challenge` missing; Critical audience formats incompatible; High Gateway JWT; High AI onboarding missing; High SDK surface missing.
- `rev-gpt-determinism`: High deploy replay API/state-machine boundary undefined; High canonical request serialization underspecified.

**Problem:** A conforming implementer can choose different contracts depending on which document they read. The most repeated conflicts are:
- MCP/Gateway auth path says JWT in some places while app-cert canonical signatures are intended as the Agent/MCP main path.
- `swarm_deploy_challenge` is required by deploy anti-replay flow but absent from public MCP/interface/reference tables.
- `DeployPayload` examples disagree on signed fields, certificate id, nonce/challenge, payload hash, metadata, and method shape.
- Certificate `audience` has incompatible formats across documents.
- Canonical request/body serialization is named but not sufficiently normative for replay/signature determinism.
- MCP/reference docs lack parameter schemas and return types for many non-auth tools.
- AI-agent onboarding references resources that do not exist or are not executable end-to-end.

**Required fixes before implementation:**
1. Declare one canonical MCP auth path: application certificate + canonical request signature for Agent/MCP; JWT only as Web/session compatibility where explicitly allowed.
2. Add `swarm_deploy_challenge` to every authoritative MCP tool inventory and reference table, or explicitly fold the challenge into a documented two-phase `swarm_deploy` operation.
3. Define one normative `DeployPayload` schema with signed fields, nonce/challenge field, certificate id, payload hash, metadata, timestamp, audience, and validation order.
4. Define one canonical certificate `audience` grammar and propagate it across auth, security, gateway, and command-source documents.
5. Specify canonical request/body serialization byte-for-byte enough for signature verification and replay determinism.
6. Expand MCP/reference schemas for non-auth tools or point to a machine-readable IDL that is within the implementation scope.
7. Add or inline an AI Agent Quickstart that actually reaches first deploy via MCP.

### B2 — Auth hot path lacks a scalable nonce/cache/per-request verification contract

**Consensus strength:** High. Performance found Critical issues; Security, API/DX, Economy, and Determinism also flagged related nonce/challenge/DoS/replay concerns.

**Representative reviewers:**
- `rev-dsv4-performance`: Critical per-request FDB nonce write amplification; Critical certificate-chain verification with no caching; High auth subspace lacks Dragonfly strategy.
- `rev-gpt-performance`: High CRL/TTL state growth; Medium certificate-chain verification cache boundary missing; Medium nonce store scaling/cleanup missing.
- `rev-dsv4-security`: High challenge DoS; missing PoW/rate-limit on unauthenticated challenge requests.
- `rev-gpt-security`: Admin/MCP unrestricted paths and recovery defaults can amplify misuse/DoS.
- `rev-gpt-determinism`: deploy replay protection references undefined API/state-machine boundary; revocation outcome flexible but not deterministic.
- `rev-dsv4-determinism`: epoch bump and wall-clock timeout semantics need clarification.

**Problem:** The design describes secure request verification primitives, but not the operational contract that prevents those primitives from overwhelming the engine path. The strongest warning is `rev-dsv4-performance`'s scale model: per-request nonce persistence in FDB could create roughly 28K auth writes/tick at MVP scale, competing with world-state transactions. Full certificate-chain verification per request also lacks a documented cache/invalidation boundary. Separately, unauthenticated challenge endpoints and admin/recovery flows need rate-limit/authorization gates.

**Required fixes before implementation:**
1. Define nonce storage as a hot-path service with bounded TTL, cleanup, cardinality, shard/bucket strategy, and crash/replay behavior.
2. Decide whether Dragonfly/Redis SETNX TTL, rolling buckets, Bloom filters, or FDB persistence is authoritative for request nonce freshness; document failure semantics.
3. Add certificate-chain verification cache rules keyed by certificate/intermediate fingerprint, with invalidation on CRL update, cert revocation, and Intermediate CA rotation.
4. Specify which auth subspaces are cached in Dragonfly, which remain FDB-authoritative, and the allowed staleness window.
5. Add rate limits / PoW / backoff for unauthenticated challenge issuance and sensitive admin/recovery endpoints.
6. Define emergency security-epoch bump operational behavior: whether running modules continue, recompile queue limits, and user-visible recovery timeline.

### B3 — Onboarding and recovery UX are not executable enough for the target AI/human audience

**Consensus strength:** Medium-high. Designer, API/DX, Economy, Security, and Architect all flagged parts of the first-hour path.

**Representative reviewers:**
- `rev-gpt-designer`: High AI-only first-hour onboarding not executable; Medium recovery/device UX lacks state guide.
- `rev-dsv4-designer`: High onboarding compressed to opaque shorthand; High referenced onboarding/auth resources do not exist; Medium certificate expiry notification and device-management gaps.
- `rev-dsv4-apidx`: High AI agent MCP onboarding undocumented; SDK API surface not specified.
- `rev-gpt-economy`: Getting Started cannot guide new players through the new cert-first deploy flow.
- `rev-gpt-security`: Recovery default keeps old certificates, unsafe for stolen-device/all-certs-lost scenarios.

**Problem:** The design has good primitives, but the user/agent journey is not yet runnable. The first deploy path requires fingerprint pinning, key generation, PoW, CSR, certificate storage, challenge/nonce, canonical payload signing, deploy, and verification. Current docs compress or omit parts of that path. Recovery and multi-device management also lack default-safe UX guidance.

**Required fixes before implementation:**
1. Add a concrete first-time setup flow for Web UI and AI/MCP users, including trust fingerprint verification, PoW progress, key storage, CSR, certificate persistence, deploy challenge, and first tick confirmation.
2. Create or inline the referenced onboarding resources: AI onboarding, auth error recovery, auth tool schema, and human-agent handoff.
3. Add certificate lifecycle UX: `expires_in` / `expiring_soon`, renewal guidance, device list, revoke lost device, last-used metadata, and safe recovery defaults.
4. Change recovery defaults so stolen-device / all-certificates-lost flows revoke old certificates by default, with explicit opt-out only for benign recovery reasons.

### B4 — Determinism/replay-affecting security outcomes need normative closure

**Consensus strength:** Medium. Determinism reviewers led this; Architect/API/DX/Security overlap via canonical serialization and revocation.

**Representative reviewers:**
- `rev-gpt-determinism`: High command ordering conflict; deploy replay API boundary undefined; canonical serialization unspecified; revocation outcome flexible but not deterministic.
- `rev-dsv4-determinism`: High epoch bump vs deployed module lifecycle ambiguous; High wall-clock timeout replay nondeterminism.
- `rev-dsv4-architect` and `rev-dsv4-apidx`: audience and deploy payload inconsistencies can break signature/replay verification.

**Problem:** Auth decisions can affect deterministic execution and replay. If revocation, epoch bumps, compile timeouts, deploy ordering, canonical serialization, or command ordering are left to implementation discretion, independent replay/validator implementations can diverge while all claiming spec compliance.

**Required fixes before implementation:**
1. Pick one RawCommand ordering contract and make it authoritative across tick protocol and command validation docs.
2. Define replay-mode behavior for wall-clock timeout and compile-time timeout paths.
3. Define deterministic outcomes for revocation reason classes: continue, freeze, rollback, reject future commands, or admin-only resolution.
4. Define security epoch bump semantics for already deployed and already running modules.
5. Ensure canonical request serialization, audience grammar, and deploy payload schema are byte-identical across implementations.

## Direction-specific High findings

### Architect

- `A-H1`: Auth Service placement remains ambiguous: Engine-internal module vs separate signing service. `rev-dsv4-architect` and `rev-dsv4-security` both prefer a separate signing boundary for Intermediate CA key operations.
- `A-H2`: TTL policy conflicts across documents: 7-day vs 180-day implications affect CRL size, renewal UX, and online state.
- `A-H3`: Blake3 MAC wording conflicts with Ed25519 code-signing model; remove or scope MAC language so implementers do not build shared-key code signing.

### Security

- `S-H1`: Intermediate CA key protection is underspecified. The online Intermediate CA is the highest-value signing component; storage, HSM/KMS/offline root, rotation, and blast-radius rules need to be explicit.
- `S-H2`: Admin recovery link generation lacks dual authorization / scoped confirmation. Admin certificates plus unrestricted MCP reference language can become a global destructive path.
- `S-H3`: CSR payload challenge field conflicts with server-authoritative challenge verification; client-supplied challenge must not be trusted.
- `S-H4`: Sandbox OS boundary text conflicts; seccomp/cgroup/no-sandbox fallback behavior must fail closed for untrusted code.

### Designer / UX

- `D-H1`: Getting Started compresses the most security-sensitive path into opaque bullets and a shorthand `swarm_deploy(module_bytes, wasm_signature)` call.
- `D-H2`: First-hour AI onboarding is not executable from the public MCP/resource surface.
- `D-H3`: Missing device/certificate management UI creates support-risk for renewal, revocation, and lost-device recovery.

### Performance

- `P-H1`: CRL/cert TTL policy can enlarge online revocation state if implementers follow the wrong table.
- `P-H2`: Federation CRL polling / fallback can create availability and hot-path latency issues.
- `P-H3`: Security epoch bump can trigger large simultaneous recompile queues; operational behavior must be defined.

### Economy

- `E-H1`: Account deletion asset transfer can become an asset cleanup/laundering path if constraints are too loose.
- `E-M1`: PoW cost floor may be too low for botnet economics, especially if account creation is economically meaningful.
- `E-M2`: Revocation and fuel-budget scope need clearer economic semantics: per-account vs per-cert vs per-agent matters.

### API/DX

- `X-H1`: Non-auth MCP tools lack parameter schemas and return types; SDK/codegen consumers cannot build against prose-only tool names.
- `X-H2`: SDK API surface, `Snapshot`, `Command`, host-function wrappers, and IDL source-of-truth need to be included or referenced normatively.
- `X-H3`: Error taxonomy is fragmented and not attached to tool schemas.

### Determinism

- `T-H1`: Command ordering conflict across specs can break replay checksums.
- `T-H2`: Wall-clock timeouts and compile-time behavior need deterministic replay exceptions.
- `T-H3`: Revocation and epoch bump semantics must not be left to runtime discretion.

## Medium / Low findings

| ID | Issue | Source directions | Recommended disposition |
|---|---|---|---|
| ML-1 | Error codes fragmented and recovery guidance sparse | API/DX, Designer | Add unified error taxonomy with retry/recovery strategy and attach to MCP schemas. |
| ML-2 | Rate limiting units and scope inconsistent | API/DX, Economy, Security | Normalize units and ownership: per account, per cert, per IP, per world. |
| ML-3 | Federation asset/ranking boundary unclear | Economy | Clarify cross-world asset non-transferability and ranking boundaries. |
| ML-4 | Certificate expiry proactive notification absent | Designer | Add `expires_in`, `expiring_soon`, renewal UX, and optional MCP event. |
| ML-5 | Web UI device-management panel not described | Designer | Add minimal UI/flow requirements; implementation can be Phase 1 but contract should exist. |
| ML-6 | Compatibility layer / Screeps migration deferred | API/DX | Accept as non-blocking if explicitly marked community/deferred; provide minimal migration note. |
| ML-7 | RUNBOOK references `swarm ca` CLI without introduction | Designer | Add pointer to operator CLI docs or avoid assuming the binary exists. |
| ML-8 | PoW slow-device UX and mobile difficulty feedback weak | Designer, Economy | Add progress explanation, capability estimate, and fallback text before long wait. |
| ML-9 | CRL cleanup / nonce cleanup lifecycle missing details | Performance, Security | Fold into B2 hot-path cache/TTL work. |
| ML-10 | World seed forward secrecy / replay privacy concerns | Determinism | Track as implementation-phase hardening unless it affects current auth contract. |

## D-items — user decisions (resolved)

### D1 — Canonical certificate `audience` grammar ✅

**Decision:** `transport:server_id:world_id:player_id`

```
mcp:swarm-us1:world7:player_abc
```

Transport-prefixed colon grammar. Per-player/per-transport binding. One canonical format across all documents.

### D2 — Request nonce authority and storage model ✅

**Decision:** Two-layer anti-replay. No `swarm_deploy_challenge`.

**Layer 1 — Version-sequence anti-replay (deploy, no nonce):**

```
Client signs: signed_at + version_counter + module_hash + metadata_hash
Server rejects: version_counter ≤ current_version_counter
Server returns: already_deployed for identical (module_hash, metadata_hash)
```

**Layer 2 — Nonce anti-replay (auth / admin / recovery):**

| Dimension | Decision |
|-----------|----------|
| Authority | Dragonfly SETNX TTL (not FDB) |
| Format | `{account_id}:{nonce_value}` → `"1"` |
| TTL | 300s default, covers network retransmit window |
| Crash semantics | Replay possible within TTL window; window expiry → replay rejected |
| Cleanup | TTL auto-expiry, no background task |

**High-value operations** (admin cert issuance, recovery) use challenge-response:
```
Server: challenge = Blake3(account_id || server_seed || timestamp)
Client: sign(challenge || request_payload)
Server: verify signature + challenge freshness (60s window)
```
Challenge not stored — recomputed on verification.

**MCP impact:** `swarm_deploy_challenge` removed from protocol. Deploy accepts signed payload directly.

| Tool | Nonce requirement |
|------|-------------------|
| `swarm_deploy` | ❌ None — version-sequence |
| `swarm_auth` / `swarm_login` | ✅ challenge-response |
| `swarm_admin_*` | ✅ challenge-response |
| `swarm_recover_*` | ✅ challenge-response |

### D3 — Auth Service deployment boundary ✅

**Decision:** Auth Service as independent process.

- All signing and authentication in a separate process from Engine.
- Engine performs trust-chain verification internally (no per-request Auth Service call for verification).
- Intermediate CA private key never shares memory with Engine.
- Non-signing certificate validation is a library call within Engine.

### D4 — Recovery default for old certificates ✅

**Decision:** Scenario-based revocation policy.

| Recovery scenario | Default behavior |
|-------------------|------------------|
| stolen-device | Revoke all old certificates |
| all-certs-lost | Revoke all old certificates |
| device-swap (old device still controlled) | Preserve; user may manually revoke |
| forgot-password (same device) | Preserve |

### D5 — Emergency security-epoch bump behavior ✅

**Decision:** Graded state machine by bump reason.

Certificate natural expiry never affects deployed modules.

| Bump reason | Module behavior |
|-------------|-----------------|
| `intermediate_ca_compromise` | `paused_security` immediately |
| `code_signing_verifier_bug` | `paused_security` immediately |
| `wasm_validation_critical` | `paused_security` or quarantine |
| `sandbox_escape_risk` | `paused_security` or quarantine |
| `wasmtime_security_update` | `needs_revalidation`; background revalidation; grace period |
| `validation_policy_update` | Same as above |
| `cache_key_epoch_bump` | Same as above |
| `crl_logic_bug` | Suspected → `paused_security`; unrelated → `needs_revalidation` |

All epoch bumps and module security state changes recorded in TickTrace.
Replay uses recorded events, never re-derives security state.

### D6 — Scope of SDK/API reference before implementation ✅

**Decision:** API complete but not frozen.

- Auth/deploy must have MVP-level input/output schemas, canonical signing format, and deploy version model for implementation and testing.
- These are implementation contracts, not long-term-stable public API.
- Full MCP reference, SDK types, IDL, and AI agent quickstart continue to evolve with implementation.
- No API freeze required before first version; API must be complete enough to run end-to-end.

## Recommended next steps

1. **Run a contract cleanup pass before implementation.** Address B1 first: auth path, deploy challenge, DeployPayload, audience grammar, canonical serialization, MCP schemas, and AI quickstart.
2. **Define the auth hot-path performance contract.** Address B2 before code: nonce store, chain verification cache, Dragonfly/FDB boundaries, rate limits, and epoch bump operations.
3. **Patch onboarding/recovery docs after the API contract is stable.** The first-hour guide should not be updated against a still-moving DeployPayload/audience schema.
4. **Close determinism semantics in the same pass.** Revocation, epoch bump, wall-clock timeout, compile timeout, and command ordering should be resolved before tests are written.
5. **Launch another clean-slate review after fixes.** Because current artifacts are unanimous on direction but not implementation readiness, the next round should validate closure rather than re-litigate the certificate model.

## Severity and verdict statistics

### Verdict distribution

| Verdict | Count | Reviewers |
|---|---:|---|
| APPROVE | 0 | — |
| APPROVE_WITH_RESERVATIONS | 0 | — |
| CONDITIONAL_APPROVE | 12 | all except `rev-dsv4-apidx`, `rev-dsv4-performance` |
| REQUEST_MAJOR_CHANGES | 2 | `rev-dsv4-apidx`, `rev-dsv4-performance` |
| REJECT | 0 | — |

### Finding counts from reviewer summaries / metadata

| Reviewer | Critical | High | Medium | Low | Total / note |
|---|---:|---:|---:|---:|---|
| rev-gpt-architect | 0 | 2 | 3 | 2 | 7 |
| rev-dsv4-architect | 2 | 3 | 4 | 2 | 11 |
| rev-gpt-security | 0 | 4 | 3 | 1 | 8 |
| rev-dsv4-security | 0 | 6 | 8 | 4 | 18 |
| rev-gpt-designer | 0 | 2 | 3 | 1 | 6 |
| rev-dsv4-designer | 0 | 2 | 3 | 4 | 9 |
| rev-gpt-performance | 0 | 2 | 2 | 1 | 5 |
| rev-dsv4-performance | 2 | 3 | 4 | 4 | 13 |
| rev-gpt-economy | 0 | 3 | 2 | 1 | 6 |
| rev-dsv4-economy | 0 | 0 | 3 | 5 | 8 |
| rev-gpt-apidx | 0 | 3 | 2 | 0 | 5 |
| rev-dsv4-apidx | 2 | 4 | 4 | 3 | 13 |
| rev-gpt-determinism | 0 | 4 | 3 | 1 | 8 |
| rev-dsv4-determinism | 0 | 2 | 3 | 3 | 8 |
| **Total** | **6** | **40** | **47** | **32** | **125** |

### Consensus strength assessment

| Theme | Directions agreeing | Model coverage | Strength | Speaker disposition |
|---|---:|---:|---|---|
| MCP/auth/API contract inconsistency | 7/7 | 2/2 | Very high | Blocker B1 |
| Deploy challenge / DeployPayload missing or inconsistent | 6/7 | 2/2 | Very high | Blocker B1 |
| Gateway JWT residue | 5/7 | 2/2 | High | Blocker B1 |
| Audience/canonical serialization mismatch | 4/7 | 2/2 | High | Blocker B1 + B4 |
| Auth hot-path nonce/cache scaling | 3/7 | 2/2 | High impact | Blocker B2 |
| AI/human onboarding incompleteness | 4/7 | 2/2 | Medium-high | Blocker B3 |
| Recovery/device lifecycle UX | 3/7 | 2/2 | Medium | High/D-item |
| Deterministic revocation/epoch/timeout semantics | 2/7 | 2/2 | Medium | Blocker B4 |
| Economy-specific transfer/sybil details | 1/7 | 2/2 | Direction-specific | High/Medium follow-up |

## Final Speaker conclusion

The clean-slate app-certificate redesign should proceed, but not yet as an implementation baseline. The design is conceptually approved; the contract is not frozen. The minimum exit criteria for the next round are:

1. No document still presents JWT as the MCP/Agent primary auth path.
2. `swarm_deploy_challenge`, `DeployPayload`, `audience`, and canonical request serialization are defined once and referenced consistently.
3. MCP tool schemas and AI onboarding are executable enough for an agent to register and deploy without guessing.
4. Nonce freshness, certificate-chain verification cache, auth subspace cache, and challenge/admin rate limits are specified with bounded performance behavior.
5. Revocation, epoch bump, command ordering, and timeout behavior are deterministic under replay.

If those conditions are met, the likely next verdict should converge to `CONDITIONAL_APPROVE` or `APPROVE_WITH_RESERVATIONS` with only implementation-phase performance/security gates remaining.
