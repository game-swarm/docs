# R42 Review Task

Read the assigned files and produce a review report. Write output to the path specified below.

## Report Format

```markdown
# R42 {Direction} Review ({Model})

## Verdict: APPROVE | CONDITIONAL_APPROVE | REQUEST_MAJOR_CHANGES | REJECT

## Critical Findings (P0/Blocker)
- [ID] Finding title
  - Files: path/file.md §§
  - Description
  - Fix direction

## High Findings
- [ID] ...

## Moderate Findings
- [ID] ...

## CrossCheck Items
- [CX-1] Issue that needs other directions to validate
```

## Rules
1. Compare docs against each other — flag contradictions
2. Flag undefined terms, broken cross-references, inconsistent naming
3. Flag design gaps — something promised but not specified
4. Be specific — cite exact section headers or line numbers
5. Flag any Rhai/Dragonfly/ClickHouse/FoundationDB references as Blocker (removed in R41)
6. Focus on your direction's concerns