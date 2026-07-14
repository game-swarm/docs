# Swarm Docs — AI Agent Guide

This file governs how AI agents work with the docs repository. Each Swarm repository is self-contained and may define its own local agent instructions.

## Repository

```
docs/
├── design/           Architecture, gameplay, modes, interface, auth, economy
├── specs/
│   ├── core/         Engine specs (tick, commands, WASM, world rules, persistence, snapshots, ECS)
│   ├── security/     Security specs (MCP, visibility, provenance, CVE-SLA)
│   ├── gameplay/     Gameplay specs (feedback loops, API IDL)
│   └── reference/    API reference (commands, host functions, MCP tools, codegen)
├── RUNBOOK.md        Operations manual
├── GETTING-STARTED.md Quick-start guide
├── AGENTS.md         This file
└── README.md         Entry point
```

## Documentation Model

```
design/*.md          Pure target state — never annotate "status: implemented" or "% done"
     ↓
specs/               Technical specs — must track design; update when design changes
     ↓
ROADMAP.md           Optional per-repository gap checklist, when present
```

- **design/** is aspirational. It describes what the system should look like, not what's currently built.
- **specs/** is the implementable contract. Every spec must trace to a design decision.
- **ROADMAP.md** is optional and repository-local. When present, it contains only gaps (critical/high/moderate) grouped into waves.

## ROADMAP Rules

- `[ ]` entries only, checkable.
- No time estimates, difficulty ratings, or descriptive wave labels.
- Completed entries are removed (not checked off).
- Each gap anchors to specific spec + code location.
- Gap IDs: `GAP-C{n}`, `GAP-H{n}`, `GAP-M{n}`.

## Domain Authority Map

| Domain | Authority |
|--------|-----------|
| API tools / RejectionReason / CommandAction / Host Functions | IDL YAML + manually maintained API Registry publication |
| Economy parameters / formulas | `specs/core/resource-ledger.md` + economy IDL schema |
| Body/structure costs | economy IDL + Registry reference table |
| Special attacks | `specs/reference/special-attack-table.md` |
| Tick schedule / ECS R/W | `specs/core/phase2b-system-manifest.md` + mod plugin policy |
| Snapshot truncation | `specs/core/snapshot-contract.md` + visibility oracle |
| Persistence/replay retention | `specs/core/persistence-contract.md` + `world.toml` config |
| Security transport/authz/rate | security specs + machine-readable Registry fields |

## Working with Design Docs

1. **design/ is the north star** — do not "simplify" design to match missing implementation.
2. **Specs must agree with design** — if design changes, update the corresponding specs.
3. **ROADMAP gaps come from spec audits** — discover gaps by comparing specs to code.
4. **Never mark design items as "done"** — only ROADMAP items can be completed/removed.
5. **When fixing a tracked gap, update the affected code repository and its local ROADMAP if one exists** — close the gap entry after merging.

## Audit Workflow

When asked "does code match docs?":

1. Identify the affected self-contained repositories: docs, engine, sandbox, gateway, frontend, or mod repositories.
2. Audit in parallel: the relevant code repository against the docs/specs that govern it.
3. Write findings into that repository's local ROADMAP if present; otherwise report them in the review output.
4. Use `grep -rn` or ripgrep for searches.

## Commit Conventions

- Format: `type: description` (docs/fix/feat/chore).
- Single-repo commits: `git add -A && git commit -m "..." && git push origin main`.
- When engine/frontend/gateway code changes accompany doc changes, the code commit and docs commit are separate PRs or sequenced: docs first, then code, then docs pointer bumps in the deploy repo.
