# rev-gpt-cross-cutting

## Verdict

Blocking. The docs contain cross-cutting authority drift in the API/IDL surface, deploy schema, command terminology, host-function contract, snapshot schema, and repository navigation. Several files also violate the repo's own target-state documentation rule, making the corpus read partly as review/history tracking rather than final specifications.

## Critical Findings

### C-C1: Game API IDL tool counts disagree with Registry and reference docs

`specs/reference/api-registry.md` declares the Game API tool count as `all_declared=57`, `active_only=53`, `rfc_gated=4`, with Play 15, Deploy 7, and Debug 8 tools (`specs/reference/api-registry.md:258`, `specs/reference/api-registry.md:279`, `specs/reference/api-registry.md:307`, `specs/reference/api-registry.md:328`, `specs/reference/api-registry.md:342`). `specs/reference/mcp-tools.md` repeats the same Registry-derived counts (`specs/reference/mcp-tools.md:29`, `specs/reference/mcp-tools.md:35`, `specs/reference/mcp-tools.md:36`, `specs/reference/mcp-tools.md:37`, `specs/reference/mcp-tools.md:42`).

`specs/reference/game_api.idl.yaml` contradicts that same surface in comments and section headers: it labels the MCP section as "46 tools" while `total_tools` is 57 (`specs/reference/game_api.idl.yaml:524`, `specs/reference/game_api.idl.yaml:528`), labels Play as 14 while listing `swarm_get_available_actions` as a fifteenth Play tool (`specs/reference/game_api.idl.yaml:795`, `specs/reference/game_api.idl.yaml:1025`), labels Deploy as 6 while listing 7 deploy tools including `swarm_list_modules` (`specs/reference/game_api.idl.yaml:1038`, `specs/reference/game_api.idl.yaml:1140`), and labels Debug as 7 while listing `swarm_explain_last_tick` as an eighth debug tool (`specs/reference/game_api.idl.yaml:1153`, `specs/reference/game_api.idl.yaml:1266`).

### C-C2: `swarm_deploy` schema is split between Registry/security docs and IDL YAML

The Registry defines `swarm_deploy` input as `{player_id, drone_id, deploy_payload, code_signature, certificate_id, version_counter, metadata}` and output as `{deploy_id, accepted, validation_errors, redb_version_counter}` (`specs/reference/api-registry.md:332`). `specs/security/mcp-security.md` gives a different example shape with `{wasm_bytes, language, version_tag, room_id}` and a response `{module_id, status, deployed_at}` (`specs/security/mcp-security.md:254`, `specs/security/mcp-security.md:256`, `specs/security/mcp-security.md:266`).

`specs/reference/game_api.idl.yaml` also diverges from the Registry by defining `swarm_deploy` input as `{player_id, drone_id, wasm_bytes, metadata}` and output including `object_store_key` (`specs/reference/game_api.idl.yaml:1041`, `specs/reference/game_api.idl.yaml:1044`, `specs/reference/game_api.idl.yaml:1046`, `specs/reference/game_api.idl.yaml:1048`, `specs/reference/game_api.idl.yaml:1053`). That conflicts with `design/interface.md`, which says all MCP tools are generated from the IDL/Registry and canonical schemas live in the Registry (`design/interface.md:9`, `design/interface.md:19`, `design/interface.md:21`).

### C-C3: CommandAction count wording is inconsistent across API docs

The API Registry states CommandAction has "10 non-combat base actions + 1 Action dispatch = 11" and that ActionRegistry does not add enum variants (`specs/reference/api-registry.md:41`, `specs/reference/api-registry.md:48`). `specs/gameplay/api-idl.md` uses the same boundary: ten non-combat commands plus `Action { type, payload }` dispatch (`specs/gameplay/api-idl.md:15`, `specs/gameplay/api-idl.md:116`, `specs/gameplay/api-idl.md:117`). `design/interface.md` also says the 11 variants are authoritative in the Registry and combat/effect actions are not top-level CommandAction variants (`design/interface.md:113`, `design/interface.md:115`).

`specs/reference/commands.md` contradicts that terminology by titling the section "11 Core + Action dispatch" and saying "以下 11 种指令对应 CommandAction enum 的非战斗基础变体" (`specs/reference/commands.md:22`, `specs/reference/commands.md:24`). That phrasing turns the Registry's 10 non-combat base actions into 11 non-combat base variants and makes the total read as 12 when Action dispatch is included.

## High Findings

### H-C1: Host-function canonical list is incomplete in the gameplay IDL spec

The Registry defines seven host functions, including `host_get_random` and `host_get_fuel_remaining` (`specs/reference/api-registry.md:463`, `specs/reference/api-registry.md:467`, `specs/reference/api-registry.md:473`). `specs/reference/host-functions.md` repeats the same seven imports and detailed signatures (`specs/reference/host-functions.md:11`, `specs/reference/host-functions.md:18`, `specs/reference/host-functions.md:19`, `specs/reference/host-functions.md:63`, `specs/reference/host-functions.md:73`).

`specs/gameplay/api-idl.md` says the host-function block is a conceptual form but then enumerates only `get_world_config`, `get_world_rules`, `get_terrain`, `get_objects_in_range`, and `path_find`, omitting random and fuel remaining (`specs/gameplay/api-idl.md:187`, `specs/gameplay/api-idl.md:189`, `specs/gameplay/api-idl.md:196`, `specs/gameplay/api-idl.md:215`). Because the same file says IDL/Registry mismatch is a compile error (`specs/gameplay/api-idl.md:11`), this partial list risks being read as an alternate IDL surface.

### H-C2: Snapshot truncation schema names drift between contract, Registry, engine design, and visibility docs

`specs/core/snapshot-contract.md` requires truncated snapshots to expose `omitted_categories` with category counts (`specs/core/snapshot-contract.md:34`, `specs/core/snapshot-contract.md:45`, `specs/core/snapshot-contract.md:56`). The Registry's `swarm_get_snapshot` output also uses `omitted_categories` (`specs/reference/api-registry.md:286`). `design/engine.md` instead says truncated snapshots expose `omitted_counts` and bucket statistics (`design/engine.md:518`).

`specs/security/visibility.md` shows the snapshot example with a singular `omitted_count` (`specs/security/visibility.md:92`, `specs/security/visibility.md:94`). The same field is singular in `specs/reference/game_api.idl.yaml` (`specs/reference/game_api.idl.yaml:556`, `specs/reference/game_api.idl.yaml:566`). These names cannot all be generated into one stable MCP/WASM schema.

### H-C3: Special-attack parameter authority is violated by `api-idl.md`

`specs/reference/special-attack-table.md` declares itself the canonical parameter table and says all design/spec/IDL docs must reference it rather than restating conflicting parameters (`specs/reference/special-attack-table.md:3`, `specs/reference/special-attack-table.md:14`). It defines `Overload` cost/range as `300 Energy`, `200 (per drone)`, range `5 (LOS required)` (`specs/reference/special-attack-table.md:21`).

`specs/gameplay/api-idl.md` simultaneously says the canonical parameters live in that table (`specs/gameplay/api-idl.md:271`) but then restates action details, including `Overload` as "消耗配额 -500k, 200 tick CD" without the canonical cost/range/LOS fields (`specs/gameplay/api-idl.md:275`, `specs/gameplay/api-idl.md:282`). The same restatement pattern appears for `Leech` damage (`specs/gameplay/api-idl.md:286`) while the canonical table's row uses a different parameter surface focused on cost/cooldown/range/channel/counterplay (`specs/reference/special-attack-table.md:25`).

## Moderate Findings

### M-C1: Root README navigation still points to removed/relocated spec paths

`README.md` advertises `specs/` as `core / security / gameplay / future` (`README.md:16`) and shows `specs/future/` plus root-level `specs/gateway-protocol.md` in the tree (`README.md:39`, `README.md:41`). The repo's actual convention says specs are grouped under `core`, `security`, and `gameplay`, with gateway protocol at `specs/security/gateway-protocol.md` (`AGENTS.md:79`, `AGENTS.md:80`).

The same convention says the former incremental snapshot and shard protocol material has been absorbed into core (`AGENTS.md:40`), and the actual files are `specs/core/incremental-snapshot.md` and `specs/core/shard-protocol.md`, not a `future/` directory. This is a cross-document navigation contradiction rather than only a missing link.

### M-C2: `PLAYTEST-GATED.md` conflicts with the repository's target-state documentation model

`AGENTS.md` prohibits status lines, dates/change markers, Phase/version markers, and design deferral language in `design/README.md`, `specs/`, and `specs/reference/` because those docs should read as finished specifications (`AGENTS.md:6`, `AGENTS.md:8`, `AGENTS.md:9`, `AGENTS.md:11`, `AGENTS.md:12`, `AGENTS.md:13`, `AGENTS.md:18`). It also says ROADMAP tracks implementation gaps while specs stay aligned to design (`AGENTS.md:44`, `AGENTS.md:49`, `AGENTS.md:56`).

`specs/gameplay/PLAYTEST-GATED.md` is under `specs/` but is explicitly a tracking/status artifact: it has a status line with a commit hash (`specs/gameplay/PLAYTEST-GATED.md:3`, `specs/gameplay/PLAYTEST-GATED.md:4`), describes blockers and closure conditions (`specs/gameplay/PLAYTEST-GATED.md:15`, `specs/gameplay/PLAYTEST-GATED.md:26`), contains a "追踪状态" table (`specs/gameplay/PLAYTEST-GATED.md:93`), and says items do not block implementation freeze but must close before release (`specs/gameplay/PLAYTEST-GATED.md:101`). This belongs in ROADMAP/review tracking, not the spec layer as currently defined.

