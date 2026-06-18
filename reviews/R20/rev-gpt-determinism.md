# R20 Determinism Review — GPT

Verdict: APPROVE

## Strengths

- IDL-first authority is explicit: `api-registry.md` is generated from `game_api.idl.yaml`, `auth_api.idl.yaml`, and `economy.idl.yaml`, and declares YAML IDL as the conflict winner.
- Replay determinism is materially improved: deploy mutations have `deploy_mutation` replay class plus `fdb_version_counter`, and tick replay records deterministic command/state/hash contracts rather than re-running WASM.
- Known non-determinism traps are addressed in the reviewed surface: fixed-point integer types replace `f64`, Blake3/XOF replaces ambient entropy, `indexmap`/stable ordering replaces `std::HashMap` iteration dependency, and Phase 2b ordering is manifest-hashed.

## 逐项判定

| ID | 状态 | 证据 |
|---|---|---|
| B19-1 RejectionReason canonical 传播 | CLOSED | `game_api.idl.yaml` defines 35 game canonical codes plus `debug_detail` as non-wire payload; `api-registry.md` carries the generated 47-code combined registry and states canonical code is the wire enum. No legacy `InsufficientResources` / `InsufficientEnergy` / `TargetNotFound` references were found in the allowed design files searched; only generic `RejectionReason` text remains. |
| B19-2 MCP/Auth tool namespace 收敛 | CLOSED | `api-registry.md` states it is generated from `auth_api.idl.yaml`, lists Auth API tools separately in §3.4, and records 12 auth RejectionReason codes at namespace offset 1000+. It also keeps game_api active MCP tools at 46 and documents auth_api as the richer auth schema source. |
| B19-3 deploy replay_class → deploy_mutation | CLOSED | `game_api.idl.yaml` sets `swarm_deploy.replay_class: deploy_mutation`; deploy section defines `mechanism: deploy_mutation` and `fdb_version_counter` replay ordering. `api-registry.md` repeats `swarm_deploy` as `deploy_mutation` and explains the manifest/hash-pointer pattern. |
| B19-4 IDL f64→fixed-point (11 fields) | CLOSED | `game_api.idl.yaml` has a fixed-point type registry replacing `f64` with `ResourceRate_i64`, `ProgressBps_i64`, `BasisPoints`, `EfficiencyBps`, `ConfidenceBps`, `milli_distance`, and `micro_cost`; registry §0 states all `f64` fields have been replaced. The reviewed game/economy API outputs use these integer/fixed-point types for rates, progress, efficiency, confidence, path distance/cost, and economy values. |
| B19-5 worker pool 256 default + 1000 hard_cap | CLOSED | `game_api.idl.yaml` limits declare `worker_pool_max: 256` as runtime default and `worker_pool_hard_cap: 1000` as compile-time hard cap; `api-registry.md` §5.5 mirrors Worker pool max 256 and hard cap 1000. |
| B19-6 经济机器源 | CLOSED | `api-registry.md` is generated from `economy.idl.yaml`, includes Economy Operations §10, Economy limits §5.7, and fixed-point economy types including `MilliUnits`; economy operations are explicitly engine-side computations, not player CommandActions. |
| U1/A auth_api.idl.yaml 独立 | CLOSED | Registry header and generation command name `auth_api.idl.yaml` as an independent source; Auth API tools and auth rejection namespace are separated from game_api. |
| U2/B economy.idl.yaml 独立 | CLOSED | Registry header and generation command name `economy.idl.yaml` as an independent source; Economy Operations and limits are sourced from economy. |
| U3/A worker_pool default 256 + hard_cap 1000 | CLOSED | Same evidence as B19-5: IDL and registry agree on runtime max/default 256 and hard cap 1000. |
| U4/A deploy_mutation replay_class | CLOSED | Same evidence as B19-3: `swarm_deploy` is now `deploy_mutation` with ordered `fdb_version_counter`. |

## State Machine Gaps

无新的阻断状态机缺口。本轮白名单中的 `/tmp/swarm-review-R20/design/architecture.md` 不存在，因此未能核验该派生文档的传播状态；但按任务约束“以 IDL YAML 为权威源”，该缺失不改变上述 CLOSED 判定。

## Non-Determinism Sources

未发现足以重开 R19 blocker 的非确定性残留。剩余需实现侧持续验证的风险是：seed 泄露后的未来 RNG 可预测性为已接受风险；对象存储异步上传失败会造成 replay/audit gap，但不破坏已提交 world state 的确定性闭包。

## GAP

GAP: 白名单中的 `design/architecture.md` 路径缺失，无法确认该派生文档是否也已传播清理。除此之外，R19 blocker 与用户裁决在 IDL 权威源和 registry 表面均已闭合。
