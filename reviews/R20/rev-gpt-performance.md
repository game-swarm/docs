# R20 性能评审（GPT）

## Verdict

APPROVE

R19 Blocker 与用户裁决在本轮白名单文档中均已闭合；以 `game_api.idl.yaml` 与派生 `api-registry.md` 为权威源核查，未发现性能方向需要继续阻塞的残留。

## Strengths

- `api-registry.md` 明确由 `game_api.idl.yaml`、`auth_api.idl.yaml`、`economy.idl.yaml` 三源生成，冲突时以 IDL YAML 为准，避免手写 Markdown 漂移。
- worker pool 权威值已收敛为运行期默认 256、编译期 hard cap 1000，并在 engine 容量推导与 registry 上限表中一致出现。
- deploy 已采用 `deploy_mutation`：WASM blob 异步进入 object store，FDB 仅提交小 manifest、hash pointer 与 `fdb_version_counter`，避免部署大对象进入 tick/FDB 热路径。
- WASM host function 全部只读且有 per-tick 调用上限、输出上限与 fuel 成本；`host_path_find` 有全局 explored-nodes 预算与 per-player fair-share。
- FDB 写入策略从全量状态转为 head/manifest/hash/pointer 小事务，大型 TickTrace/keyframe 进入对象存储或 append-only log，降低单 tick 事务争用风险。

## 逐项判定

| ID | 状态 | 证据 |
|---|---|---|
| B19-1 | CLOSED | `api-registry.md` §2 将 RejectionReason 定义为 canonical code + `debug_detail`，命名规范收敛 `InsufficientResource`、`ObjectNotFound`、`CooldownActive`、`NotVisibleOrNotFound`；`02-command-validation.md` §3 与 §5 引用 canonical RejectionReason，并把旧细节类错误降为 `(debug_detail)`。 |
| B19-2 | CLOSED | `api-registry.md` header 明确由独立 `auth_api.idl.yaml` 生成，并在 §3.4 列出 11 个 Auth API 工具；Auth 工具独立来源为 `auth_api.idl.yaml`。性能方向仅核查 namespace 收敛，不评审 auth 设计本身。 |
| B19-3 | CLOSED | `game_api.idl.yaml` `swarm_deploy.replay_class: deploy_mutation`，并在 `deploy.mechanism: deploy_mutation` 中定义 `fdb_version_counter`；`api-registry.md` §3.2/§11 同步显示 `swarm_deploy` 为 `deploy_mutation`。 |
| B19-4 | CLOSED | `game_api.idl.yaml` type registry 明确所有 f64 已替换为 fixed-point 类型；可见字段包括 `ResourceRate_i64`、`ProgressBps_i64`、`BasisPoints`、`EfficiencyBps`、`ConfidenceBps`、`milli_distance`、`micro_cost`，registry §0 同步列出跨 IDL fixed-point registry。 |
| B19-5 | CLOSED | `game_api.idl.yaml` `limits.hardware_baseline.worker_pool_max: 256` 与 `worker_pool_hard_cap: 1000`；`api-registry.md` §5.5 同步列出默认 256 与 hard cap 1000；`engine.md` §3.4.2 使用同一数值推导。 |
| B19-6 | CLOSED | `api-registry.md` header 与 §10 明确 economy 来源为独立 `economy.idl.yaml`，并列出 `RecycleRefund`、`StorageTax`、`UpkeepDeduction`、`PvEAward`、`BuildCost`、`SpawnCost`、`AlliedTransfer` 等经济操作及 canonical formulas。 |
| U1/A | CLOSED | `api-registry.md` header/§3.4 显示 Auth API 独立 IDL 源；非性能方向，判定为已传播。 |
| U2/B | CLOSED | `api-registry.md` header/§10 显示 Economy API 独立 IDL 源；经济操作使用整数/定点类型，无 f64。 |
| U3/A | CLOSED | worker pool default 256 + hard cap 1000 在 IDL、registry、engine 容量推导三处一致。 |
| U4/A | CLOSED | `swarm_deploy` replay_class 与 deploy mechanism 均为 `deploy_mutation`，且配套小 FDB manifest 与 object-store 异步上传。 |

## Concerns

- P2: `02-command-validation.md` 后半仍保留若干旧示例文字（如 Recycle 固定 50% 退还、局部表格格式残留），但同文档上游与 `api-registry.md`/IDL 权威源已给出 lifespan-proportional 公式；不构成 R20 blocker。
- P2: `01-tick-protocol.md` 中 EXECUTE 超时示意存在 500ms/预算表软截止语义差异，但 R20 验证目标是 R19 残留传播闭合，未形成新的性能阻塞。

## Bottleneck Analysis

- Tick 关键路径：COLLECT 仍是主瓶颈，但 worker pool 默认 256、hard cap 1000、aggregate CPU admission、per-player fuel cap 与 soft/hard deadline 已形成闭环；1000 active players 场景通过 fuel throttling 与 admission gating 控制，而非承诺每玩家高配额。
- ECS 调度：Phase 2b 的 serial spine + parallel sets 已明确，Combat 与 Status Effects 有分区并行策略；R20 未读取 manifest 文件（不在白名单），但白名单文件中的引用和摘要足以证明旧“调度残留”已传播到主设计与 tick spec。
- WASM 开销：fuel metering、epoch interruption、64MB linear memory、128MB cgroup、host call 1000/tick/player、path_find 10/tick 与输出 256KB 均有硬上限；未发现无界 host operation。
- FDB 热点：deploy 与大 blob 已移出 FDB 热路径，tick commit 只保留小事务/manifest/hash/pointer；这比 R19 前的 blob/全量状态写入模型更合理。

## Throughput Estimates

- Target 500 active players：按 `engine.md` 推导，p50 5ms/player 在 2500ms COLLECT 预算下达到饱和边界；256 worker 默认下约 2 players/worker，需依赖 fair-share 与排队吸收 p99。
- Hard cap 1000 active players：IDL/registry 将其定义为硬上限而非舒适运行点；`engine.md` 将 per-player 可用执行时间估为约 2ms，并要求运营显式提高 `worker_pool_max > 256` 后承担容量证明。
- 1000 drones：低于 `global_drone_cap: 10000`，在当前预算模型下不是主瓶颈；风险更多来自活跃玩家数、pathfinding 全局 100,000 nodes/tick 与 snapshot 256KB/player，而这些已有硬上限和 deterministic reject。

## GAP

无阻塞 GAP。仅建议后续非阻塞清理 `02-command-validation.md` 中旧示例文字，避免读者误以为其覆盖 IDL/registry 权威源。
