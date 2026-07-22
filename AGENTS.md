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
- **design/** owns every externally observable behavior, default, protocol boundary, trust decision, and compatibility policy. It must be self-contained and must not use specs, IDL, Registry, or current code as an authority.
- **specs/** is the implementable contract. Every spec must trace to a design decision. Specs may add internal encoding, data-structure, storage-layout, and execution detail only when that detail does not change external behavior.
- **ROADMAP.md** is optional and repository-local. When present, it contains only gaps (critical/high/moderate) grouped into waves.

## ROADMAP Rules

- `[ ]` entries only, checkable.
- No time estimates, difficulty ratings, or descriptive wave labels.
- Completed entries are removed (not checked off).
- Each gap anchors to specific spec + code location.
- Gap IDs: `GAP-C{n}`, `GAP-H{n}`, `GAP-M{n}`.

## Domain Authority Map

| Domain | Design authority | Derived contract |
|--------|------------------|------------------|
| API semantics / tools / errors / ABI behavior | `design/interface.md` + `design/auth.md` | IDL YAML + API Registry publication |
| Economy parameters / formulas | `design/gameplay.md` + `design/economy-balance-sheet.md` | Resource Ledger + economy IDL |
| Body / structure sets and costs | `design/gameplay.md` | economy IDL + Registry reference tables |
| Special actions and configurable parameters | `design/gameplay.md` | special-attack table + world-rules schemas |
| Tick schedule / command order / ECS R/W | `design/engine.md` + gameplay plugin scheduling decisions | phase2b system manifest + command/tick specs |
| Snapshot, truncation, and ABI codec | `design/engine.md` + `design/interface.md` | snapshot contract + visibility contract + game IDL |
| Persistence / replay / shard migration | `design/architecture.md` + `design/engine.md` + `design/tech-choices.md` | persistence, incremental snapshot, and shard contracts |
| Security transport / Auth REST / certificate behavior | `design/auth.md` + `design/interface.md` + `design/architecture.md` | security specs + Auth IDL + Gateway fields |
| World / Arena / PvE mode behavior | `design/modes.md` + `design/gameplay.md` | gameplay specs + world-rules and mod schemas |

## Working with Design Docs

1. **design/ is the north star** — do not "simplify" design to match missing implementation.
2. **Specs must agree with design** — if design changes, update the corresponding specs.
3. **Never repair design from a spec** — resolve design conflicts first, then regenerate or edit downstream contracts.
4. **ROADMAP gaps come from spec audits** — discover gaps by comparing specs to code.
5. **Never mark design items as "done"** — only ROADMAP items can be completed/removed.
6. **When fixing a tracked gap, update the affected code repository and its local ROADMAP if one exists** — close the gap entry after merging.

## Audit Workflow

When asked "does code match docs?":

1. Verify that the relevant specs first agree with their upstream design decisions.
2. Identify the affected self-contained repositories: docs, engine, sandbox, gateway, frontend, or mod repositories.
3. Audit in parallel: the relevant code repository against the derived specs that govern it.
4. Write findings into that repository's local ROADMAP if present; otherwise report them in the review output.
5. Use `grep -rn` or ripgrep for searches.

## Commit Conventions

- Format: `type: description` (docs/fix/feat/chore).
- Single-repo commits: `git add -A && git commit -m "..." && git push origin main`.
- When engine/frontend/gateway code changes accompany doc changes, the code commit and docs commit are separate PRs or sequenced: docs first, then code, then docs pointer bumps in the deploy repo.
