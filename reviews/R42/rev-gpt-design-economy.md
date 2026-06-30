# R42 Design & Economy Review (GPT-5.5)
## Verdict: REQUEST_MAJOR_CHANGES

## Critical Findings (P0/Blocker)
- [D-H1] Balance sheet cannot be derived from the declared economic authority.
  - Files: `design/economy-balance-sheet.md:3-5`, `design/economy-balance-sheet.md:35-40`, `design/economy-balance-sheet.md:44-61`, `design/economy-balance-sheet.md:65-83`, `design/economy-balance-sheet.md:87-152`, `specs/core/resource-ledger.md:70-100`, `specs/core/resource-ledger.md:120-150`, `specs/core/resource-ledger.md:187-218`
  - Description: The balance sheet claims Resource Ledger is the sole source for rates/formulas, but its break-even proof depends on independent assumptions for source income, controller passive income, source levels, code-efficiency multipliers, and room/source counts. Resource Ledger does not define those inputs, and its growth-path example uses controller income `50/tick`, conflicting with the balance sheet's RCL1 `2/tick`. The 1-room table also counts free upkeep as `+55` income while expenses are already `0`, inflating net flow from the stated base income.
  - Fix direction: Put every balance-sheet input into the authoritative economy spec, or restrict the balance sheet to values already defined there. Model free upkeep only as an expense waiver, and define one canonical source/controller/PvE income table before asserting the 2-10 room target curve.

- [D-H2] Default build/body cost tables conflict across design, spec, and registry.
  - Files: `design/gameplay.md:112-229`, `design/gameplay.md:845-903`, `specs/core/world-rules.md:330-393`, `specs/core/world-rules.md:439-588`, `specs/gameplay/api-idl.md:173-181`, `specs/reference/api-registry.md:855-856`
  - Description: Default structures are duplicated with different membership and costs. `design/gameplay.md` lists 13 structures and omits Road/Wall/Rampart/Container, while `world-rules.md` and API Registry define those as buildable defaults. Costs also diverge: PowerSpawn is 5000 in design vs 1200 in world-rules/registry, Nuker is 100000 vs 5000, Depot is 5000 vs 600. Body costs diverge for RangedAttack: world-rules says 100, while design/API/registry say 150.
  - Fix direction: Make one table the canonical default content/cost authority and convert all other files to references or exact generated excerpts. The default structure set and body costs must match byte-for-byte across design/spec/reference.

## High Findings
- [D-H3] World PvE defines direct rewards outside the PvEAward budget path.
  - Files: `design/modes.md:32-69`, `specs/core/resource-ledger.md:187-218`
  - Description: World PvE says NPC drops reference Resource Ledger tiers, but the same section defines direct Swarmling drops, Guardian Wreckage recovery, fixed resource-point payouts, and regeneration rates. Resource Ledger defines PvE output through `PvEAward` tiers and Global/Zone/Player/Event budgets, with no Wreckage operation or explicit resource-point budget treatment.
  - Fix direction: Route every PvE resource emission through Resource Ledger operations. Add Wreckage/resource-point emissions as explicit budgeted `PvEAward` mappings, or remove fixed direct rewards from `design/modes.md`.

- [D-H4] Leech and Fabricate mechanics contradict the canonical action table and scheduler.
  - Files: `design/gameplay.md:737-750`, `design/gameplay.md:1194-1210`, `specs/core/phase2b-system-manifest.md:244-270`, `specs/core/phase2b-system-manifest.md:272-303`, `specs/gameplay/api-idl.md:280-287`, `specs/reference/special-attack-table.md:24-26`
  - Description: The canonical table gives Leech cooldown `100`, while gameplay lists `150`. The manifest models Leech as resource/age transfer and explicitly avoids PendingDamage, while gameplay/API describe Kinetic damage plus 50% self-heal. Fabricate is also split between `2000 Energy + 500 Matter` in the canonical table and gameplay concept table, but the gameplay TOML excerpt omits Matter; the manifest describes body-part modification rather than enemy-drone-to-structure conversion.
  - Fix direction: Choose one semantic model for each action and update the canonical table, gameplay concept text, TOML excerpt, API summary, and manifest buffers to match. Remove local restatements where possible.

- [D-H5] Arena victory conditions drift between mode design and feedback-loop spec.
  - Files: `design/modes.md:21-24`, `design/modes.md:144-149`, `specs/gameplay/feedback-loop.md:333-342`
  - Description: `design/modes.md` defines configurable Arena victory conditions (`fixed_ticks`, structure destruction, full wipe, capture points), while feedback-loop reduces Arena to destroying the enemy Spawn or winning by score at time limit.
  - Fix direction: Make feedback-loop reference the configurable victory-condition set from modes, or define the reduced Spawn/score rule as the single canonical Arena default and update modes accordingly.

## Moderate Findings
- [D-M1] Target-state docs still contain review/progress markers and deferred-language.
  - Files: `design/economy-balance-sheet.md:3-5`, `design/gameplay.md:405-417`, `design/modes.md:83-85`, `design/modes.md:150`, `specs/core/resource-ledger.md:5-9`, `specs/core/resource-ledger.md:305-313`, `specs/core/phase2b-system-manifest.md:5-7`, `specs/core/phase2b-system-manifest.md:511-517`, `specs/gameplay/feedback-loop.md:342`, `specs/reference/api-registry.md:964-975`
  - Description: The reviewed design/spec/reference docs include R-fix notes, changelogs with dates, "远期", "Out-of-Scope", RFC/deferred language, and Stage wording. The repo convention requires these files to read as target-state specs, with history in git and implementation tracking in ROADMAP/reviews.
  - Fix direction: Remove history/status/deferred markers from design/spec/reference files. Express only the target rules, and move unresolved or excluded work to ROADMAP or review artifacts.

- [D-M2] Float examples remain in rule schemas despite fixed-point requirements.
  - Files: `specs/core/world-rules.md:49-59`, `specs/core/world-rules.md:101-109`, `specs/core/world-rules.md:921-977`, `specs/reference/api-registry.md:20-33`, `design/gameplay.md:1612-1614`
  - Description: The registry and gameplay determinism contract require fixed-point/integer numeric modeling, but world-rules examples still use `decay_rate = 0.0`, `0.001`, `transfer_to_global_cost = { Energy = 0.01 }`, `transfer_from_global_cost = { Energy = 0.05 }`, and permit `f64` in mod config types.
  - Fix direction: Rewrite schema examples and allowed mod parameter types to use bp/ppm or explicit fixed-point integer types. Remove `f64` from deterministic world-rule state transitions.

## CrossCheck Items
- Checked only the requested files plus the existing target report file.
- No finding is based on unreviewed source content.
- Broken-link/stale-reference check found many history/RFC/status markers; only the ones that materially violate the target-state document convention are listed above.
- The most important duplicate tables are structure/body costs and vanilla action parameters; both have live contradictions that should be resolved before approval.
