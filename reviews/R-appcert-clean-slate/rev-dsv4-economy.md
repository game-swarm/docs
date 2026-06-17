# R-appcert-clean-slate: rev-dsv4-economy Review

**Reviewer**: rev-dsv4-economy (DeepSeek V4 Pro — Economy Focus)
**Date**: 2026-06-17
**Scope**: Clean-slate review of Swarm authentication redesign — account/device/certificate policy impact on game economy, agent deployment, federation identity/asset isolation
**Documents Reviewed**:
- `design/README.md` (full) — system architecture, federation philosophy
- `design/auth.md` (full, 1508 lines) — auth system, CSR, certificates, recovery, federation
- `design/interface.md` (full) — MCP tools, game API
- `design/tech-choices.md` (full) — technology stack rationale
- `design/gameplay.md` (partial, §8, §resources, §economy) — game mechanics, resource model, storage tiers
- `design/engine.md` (full) — tick lifecycle, ECS, entity model
- `design/modes.md` (full) — World vs Arena, PvE economy
- `GETTING-STARTED.md` (full) — onboarding flow
- `RUNBOOK.md` (full) — operational procedures
- `specs/12-gateway-protocol.md` (full) — transport auth matrix
- `specs/reference/mcp-tools.md` (full) — MCP tool catalog
- `specs/security/03-mcp-security.md` (full) — MCP security constraints
- `specs/security/09-command-source.md` (full) — command source model, deploy nonce
- `specs/core/04-wasm-sandbox.md` (full) — WASM sandbox, fuel metering

**Excluded per task**: reviews/, ROADMAP, .git history, temporary files

---

## Verdict: CONDITIONAL_APPROVE

The authentication redesign is architecturally sound and introduces well-reasoned economic protections (progressive storage tax, federation asset isolation, PoW anti-sybil). The certificate model's "expired certs don't kill deployed modules" semantic is critical for autonomous agents and correctly preserves economic continuity. However, **three Medium-severity issues + five Low-severity gaps concerning multi-account economics, certificate revocation's economic impact, and agent-managed key risks must be addressed before Phase 1 implementation** — preferably in a focused addendum to `design/auth.md` rather than a redesign.

No Critical or High findings. All blockers are resolvable within the current design framework without architectural rework.

---

## Strengths

1. **Certificate expiration does not disrupt economic activity.** `CodeSigningCertificate` expiration after deployment does not stop already-running WASM modules — this is the single most important property for autonomous AI agents whose economic output depends on continuous uptime. Design/auth.md §5.4 explicitly states this contract.

2. **Federation identity model with per-world asset isolation** correctly prevents economic contamination. A wealthy player on World A cannot carry their economic power to World B — they must re-earn it. Design/auth.md §15.4 explicitly states "独立本地 player_id 和资产". This is correct and well-defended.

3. **Progressive Storage Tax** (design/gameplay.md §Global Storage Anti-Dominant-Strategy) is an elegant anti-monopoly mechanism with three reinforcing pillars: tax tiers, local storage stealth, and no-teleport logistics. Good design that accounts for economic snowballing.

4. **Account deletion with configurable asset disposition** (abandon/recycle/transfer) provides clean economic exit paths with Ed25519-signed transfer acceptance — preventing fraudulent asset grabs. Design/auth.md §13.1/13.4.

5. **Agent proxy registration handoff protocol** (§4.3) with one-time handoff codes prevents chat-log credential leaks. This directly protects agent-managed economic assets from exposure.

6. **PoW as rate control** coupled with `username_visibility` modes shows thoughtful trade-off design for anti-sybil. The separation of CSR PoW from recovery PoW (disabled by default) is correct.

7. **WASM fuel metering + defer-only command model** ensures AI agents and human players compete on equal economic terms — no MCP-based gameplay advantage. Consistently enforced across all specs.

8. **PvE economic constraints** (design/modes.md §NPC 掉落经济: `max_pve_output_per_tick ≤ world regeneration × 30%`) prevent PvE farming from overwhelming PvP economic value. Good guardrail.

---

## Findings

### Finding E1 — Medium: Account creation cost floor is too low for economic anti-sybil

**File**: `design/auth.md` §9.2
**Severity**: Medium
**Category**: Security gap / deferred implementation concern
**Evidence**: PoW difficulty defaults to 24 bits (~16.7M attempts, ~150ms Rust, ~3s browser WASM). The energetic/electric cost of solving this PoW is negligible — approximately $0.0001 in CPU electricity cost. An attacker can create thousands of accounts for under $1.

**Impact**: In a game economy where accounts control resource-producing drones, a botnet of 1,000 accounts could harvest resources at 1,000× the rate of a single account. The progressive storage tax (§anti-dominant-strategy) mitigates this for *global storage*, but not for *local storage* (which is private and untaxed). A sophisticated attacker would keep resources in local storage (stealth advantage) and never trigger global storage tax.

**Design gap**: The current anti-sybil model is purely PoW-based with no economic stake requirement. There is no:
- Minimum resource deposit to activate an account
- Per-account spawn cooldown that scales with world player count
- Resource cost for certificate issuance (certificates are free)
- Account age-based economic scaling

**Recommendation**: Add a configuration option for "account activation resource cost" — a one-time resource deposit returned to the world economy (not the player) when the account first spawns. Even 500 Energy would make botnet economics unviable while remaining trivial for real players. Alternatively, consider scaling `spawn_cooldown` with total world player count to create a natural anti-bot throttle.

### Finding E2 — Medium: Certificate revocation economic impact is underspecified

**File**: `design/auth.md` §5.4; `specs/security/09-command-source.md` §3.4
**Severity**: Medium
**Category**: Doc inconsistency / security gap
**Evidence**: Both documents state that certificate revocation "按 revocation reason 冻结、回滚或继续允许既有模块运行" (freeze, rollback, or continue running based on revocation reason). However:

1. **No decision tree is specified** — which reason maps to which action? If `reason=key_compromise`, should all economic output of that certificate's modules be rolled back? If so, how far back?
2. **No economic grace period** — a revoked cert instantly stops the owner from deploying new code, but what about their existing drones/buildings? They continue running because the cert isn't needed per-tick. But the owner can't *change* their strategy — they're economically frozen while their assets potentially get destroyed by other players.
3. **Admin credential abuse** — `AdminCertificate` revocation has no economic countermeasure defined. A compromised admin could revoke certificates of economic rivals.

**Consistency gap**: `design/auth.md` §5.4 says "按 revocation reason 冻结、回滚或继续允许既有模块运行" while `specs/security/09-command-source.md` §3.4 says "证书吊销是安全事件，服务器按 revocation reason 冻结、回滚或继续允许既有模块". Both defer to an unspecified revocation reason → action mapping.

**Recommendation**: Define a concrete revocation-to-action matrix:
- `lost_device`: Continue existing modules, block new deploys. No grace period needed — user still has other devices/certs.
- `key_compromise`: Freeze all modules (stop executing at next tick). Allow re-deploy with new cert within a grace period (e.g., 300 ticks). After grace, recycle assets per account deletion policy.
- `admin_action`: Same as key_compromise but with mandatory admin audit trail.
- `federation_policy`: Accept-login only; existing local modules continue.

### Finding E3 — Medium: Multi-device certificate model creates economic multi-boxing without countermeasures

**File**: `design/auth.md` §5.5
**Severity**: Medium
**Category**: Security gap
**Evidence**: "用户可以要求服务器为同一账号签发任意多个同时有效的证书" (users can request any number of simultaneously valid certificates for the same account). Combined with multi-device support using different `device_label` values, this enables one account to control drones from multiple "devices" that are actually different machines.

**Impact**: While certs are per-account (not per-device in terms of player identity), the multi-device model with different labels creates no *economic* friction for running multiple WASM instances per account. If there's a per-player fuel cap (10M fuel/tick), running multiple sandbox workers under the same account could split the cap. But if fuel is per-account, there's no advantage. **The document does not clarify whether fuel budget is per-account or per-certificate**.

**Cross-reference**: `specs/core/04-wasm-sandbox.md` §6 shows `MAX_FUEL = 10M` but does not specify whether this is per-player, per-certificate, or per-sandbox-instance.

**Recommendation**: Clarify in `design/auth.md` §5.5 that:
1. Fuel budget is **per-player (per-account)**, not per-certificate
2. Multiple simultaneously active sandbox workers under the same account share the fuel pool
3. Document this in `specs/core/04-wasm-sandbox.md` §6 as well

### Finding E4 — Low: Agent-managed key mode has unbounded economic liability

**File**: `design/auth.md` §4.3
**Severity**: Low
**Category**: UX gap / deferred implementation concern
**Evidence**: Agent proxy registration (§4.3) offers two modes: "Agent 托管模式" (agent holds keys long-term) and "人类自管模式" (human imports, agent discards). In Agent 托管模式, the agent "可长期持有私钥代为操作". If the agent is compromised, the attacker gains full economic control — deploy, transfer, delete account.

**Gap**: There is no discussion of:
- Maximum economic value exposure limits for agent-managed keys
- Transaction confirmation requirements for high-value operations (transfer, account deletion)
- Insurance/escrow mechanisms
- Agent compromise detection heuristics (e.g., unusual deploy patterns)

**Recommendation**: Add to `design/auth.md` §4.3 a note about optional "spending limits" or "multi-signature thresholds" for agent-managed accounts. This can be deferred to post-Phase-1 but should be acknowledged as a known risk.

### Finding E5 — Low: Account transfer asset disposition has a deadlock risk

**File**: `design/auth.md` §13.4
**Severity**: Low
**Category**: API gap / UX gap
**Evidence**: `swarm_delete_account` with `asset_disposition = "transfer"` requires the recipient to provide Ed25519-signed acceptance within 5 minutes (§13.4: "检查时间戳在 5 分钟内"). If the recipient is an AI agent whose certificate has expired and hasn't been renewed, or if the recipient is offline, the transfer fails with `transfer_rejected`.

**Impact**: The deleting player cannot complete their account deletion and release their `login_username` until the recipient is available and signs. This creates an economic deadlock.

**Recommendation**: Add a fallback disposition: if `transfer_rejected`, fall back to `recycle` (default 50% refund) instead of blocking deletion. Document this in §13.4.

### Finding E6 — Low: Federation revocation fallback has unexamined economic consequences

**File**: `design/auth.md` §15.6
**Severity**: Low
**Category**: Doc inconsistency
**Evidence**: Federation revocation fallback offers three policies: `reject_for_code`, `accept_login`, `reject_all`. When set to `reject_all`, a player actively trading cross-world could lose their local economic position — their local code stops running, their drones idle, and their assets become vulnerable.

**Gap**: The document does not discuss whether `reject_all` triggers the same asset disposition pipeline as account deletion, or whether the player's assets simply become "frozen" (drones idle, buildings decay). The distinction matters enormously for economic fairness.

**Cross-reference**: §15.6 mentions "记录 WARN 日志" for `accept_login` but no monitoring guidance for `reject_all`.

**Recommendation**: Clarify that federation revocation only affects *authentication* (new deploys, new certs) and does not retroactively affect already-deployed modules. This aligns with the general certificate expiration semantics in §5.4. Add a monitoring alert for `reject_all` triggering.

### Finding E7 — Low: No economic cost for certificate issuance enables registration spam

**File**: `design/auth.md` §3.1, §10.3
**Severity**: Low
**Category**: Security gap / deferred implementation concern
**Evidence**: `issue_certificate_bundle()` and `swarm_submit_csr` issue certificates with no resource cost to the player. PoW is a one-time cost per registration. Certificates themselves — `ClientAuthCertificate`, `CodeSigningCertificate`, `AdminCertificate` — are issued for free.

**Impact**: Combined with Finding E1 (low PoW cost), this means each account gets unlimited free certificates. While certs are per-account and don't directly create economic advantage, the absence of cost means there's no economic disincentive to requesting the maximum number of certificates per device type.

**Recommendation**: Consider making certificate issuance consume a minimal resource amount (e.g., 100 Energy per cert) that is deducted from the player's global storage. This creates a natural economic throttle without being punitive. Mark as optional / configurable.

### Finding E8 — Low: PoW difficulty static across device classes creates unequal economic entry barrier

**File**: `design/auth.md` §9.2
**Severity**: Low
**Category**: UX gap
**Evidence**: PoW table shows ~150ms for Rust native vs ~3s for browser WASM on mobile at difficulty_bits=24. This means mobile users pay a 20× higher time cost to enter the game economy. Since Swarm is a persistent world game, early entry advantage is significant — mobile users are systematically disadvantaged.

**Gap**: The design does not mention adaptive difficulty based on device class or a CAPTCHA alternative for slow devices. 

**Recommendation**: Document this as a known UX trade-off in §9.2. Consider a "fast path" for mobile users using a server-verified CAPTCHA (e.g., Turnstile) as an alternative to PoW, configurable by server operator. Mark as deferred / optional.

---

## Consistency Gaps

### CG1: Fuel budget scoping — per-account vs per-certificate

**Files**: `specs/core/04-wasm-sandbox.md` §6, `design/auth.md` §5.5
**Issue**: WASM sandbox spec defines `MAX_FUEL = 10M` without specifying the scoping unit. Auth spec allows multiple simultaneous certificates per account (§5.5). If fuel is per-certificate, multi-device certs create a fuel multiplier. If per-account, the multi-cert model has no economic scaling issue. **Resolution needed before implementation.**

### CG2: Certificate revocation → economic disposition mapping

**Files**: `design/auth.md` §5.4, `specs/security/09-command-source.md` §3.4
**Issue**: Both files defer the revocation-reason-to-economic-action mapping to an unspecified decision tree. This is the core of Finding E2.

### CG3: Auth subspace mentioned in design but absent from data model spec

**Files**: `design/auth.md` §6.2 (FDB auth subspace), `design/README.md` §3 (data model)
**Issue**: `design/README.md` §3 only lists world state, hot cache, tick trace, and analytics in the data model table. The auth subspace (`auth/users/`, `auth/certificates/`, etc.) is defined in `design/auth.md` §6.2 but not reflected in the README's data model overview. Minor but creates confusion about where authentication data lives.

### CG4: Audience binding terminology drift

**Files**: `specs/12-gateway-protocol.md` §9 (transport auth matrix), `specs/security/09-command-source.md` §7.0
**Issue**: Gateway protocol §9 uses audience values like `rest`, `ws`, `mcp`, `replay`. Command source spec §7.0 describes audience as `mcp:{server_id}:{world_id}:{player_id}`, `ws:{server_id}:{world_id}:{player_id}`. The granularity levels are inconsistent — the transport auth matrix has flat audience values while the command source spec has structured ones. Which format does the certificate's `audience` field actually use?

---

## Questions / Assumptions

1. **Assumption**: Fuel budget (10M fuel/tick) is per-player-account, not per-certificate. Multi-device certificates do not multiply fuel allocation. *Needs explicit confirmation in docs (see CG1).*

2. **Assumption**: The game economy has no per-player resource caps beyond global storage capacity — a wealthy player can continue to accumulate wealth indefinitely (subject to progressive tax). This is the intended sandbox philosophy per `design/README.md` §1.1. *Confirmed by progressive tax design.*

3. **Question**: Are there plans for an "economic audit trail" linking certificate operations to economic events? E.g., when an admin creates a recovery link for a player, should the associated economic impact (modules deployed while that player was locked out) be tracked? *Not found in current docs — suggested as post-Phase-1 enhancement.*

4. **Question**: How does the system handle the case where a player with `managed_by_server=true` certificates has accumulated significant economic assets, and then the server operator revokes those certificates? The operator technically controls the private key. Is there a governance model for this? *Not found — see Finding E4.*

5. **Assumption**: Arena mode tournaments use the same certificate model. Tournament-specific economic concerns (e.g., prize pools in Energy/Crystal, tournament entry fees) are not addressed in auth docs. *This is acceptable — tournament economy belongs in gameplay/modes doc, not auth.*

6. **Question**: In federation model §15.2, when a player federates from World A to World B, do their certificates on World A remain valid? The doc says "不共享游戏状态、不共享模块、不共享排名" but doesn't discuss whether federation login invalidates or downgrades source-world certificates. *Assumed: No, certificates on both worlds remain independently valid.*

---

## Summary

The authentication redesign provides a robust foundation for game economy integrity. The certificate-based model correctly decouples identity from economic continuity (expired certs don't kill modules). The three Medium findings (E1-E3) are resolvable with targeted specification additions — none require architectural changes. The five Low findings are documentation gaps and deferred implementation concerns that can be addressed incrementally.

**Prioritized action items before Phase 1 implementation:**

1. **Clarify fuel budget scope** (CG1/Finding E3) — per-account, not per-certificate
2. **Define certificate revocation → economic action matrix** (Finding E2/CG2) — freeze/rollback/continue per revocation reason
3. **Evaluate PoW difficulty vs botnet economics** (Finding E1) — add configurable account activation cost
4. **Fix audience binding terminology drift** (CG4) — unify structured vs flat audience formats
5. **Add account transfer fallback disposition** (Finding E5) — fallback to recycle on transfer_rejected
