# R21 Game Design Review — B20-1 Propagation Check

**Reviewer**: rev-dsv4-designer (Game Designer)
**Date**: 2026-06-18
**Target**: B20-1 residuals in design/interface.md after R20 fix

## Verdict: CLOSED

All 4 B20-1 propagation targets verified clean in design/interface.md with api-registry.md cross-validation:

1. **MCP tools table**: Converted to conceptual category overview with canonical pointer to api-registry.md §3 (line 19-21); no full-table duplication.
2. **swarm_deploy replay_class**: Confirmed `deploy_mutation` at interface.md:158, matched by api-registry.md:277.
3. **RejectionReason count**: 47 canonical codes (35 game + 12 auth) at interface.md:118, fully aligned with api-registry.md §2.
4. **Phantom tools**: swarm_get_schema, swarm_submit_csr, swarm_token_refresh, swarm_change_password, swarm_federated_login — all absent from api-registry.md authority tables; explicitly listed as removed in interface.md:33.

## Evidence

design/interface.md now operates as a high-level conceptual narrative with all canonical detail delegated to api-registry.md — the single-source-of-truth pattern is intact. No B20-1 residuals detected.
