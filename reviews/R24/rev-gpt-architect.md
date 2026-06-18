# R24 Closure Verification — 架构评审 (GPT-5.5)

Verdict: APPROVE

## Strengths

- R24 变更把 R23 架构 blocker 从“设计意图”推进到了可执行合同：经济启动、确定性排序/执行、容量边界均有权威源与参数。
- 文档分层比上一轮更清晰：经济数值以 `08-resource-ledger.md` / registry 为准，确定性合同以 `01-tick-protocol.md` + `06-phase2b-system-manifest.md` 为准，容量上限以 `api-registry.md` §5 为准。
- 关键参数不再只靠叙述：starting resources、free upkeep、active player cap、worker pool、resource budget、sort key 都具备明确数值或公式。

## Concerns

[A1] No new concerns reviewed. 本轮为 Closure Verification，仅验证指定 R23 items，不做开放式新发现。

## Missing

None for architecture-scoped R23 items B1/B3/B4.

## Verification Items

[B1] CLOSED — World 经济启动已闭合。

Evidence:
- `/tmp/swarm-review-R24/specs/core/08-resource-ledger.md:116` 明确记录 R23 D1/A 裁决：第一个 controller 和前 N 个 drone 免维护费。
- `/tmp/swarm-review-R24/specs/core/08-resource-ledger.md:118` 明确指出 Standard World 若无初始资源与免维护期会进入 upkeep deficit 死亡螺旋，并以此定义启动经济。
- `/tmp/swarm-review-R24/specs/core/08-resource-ledger.md:124` 定义 `starting_resources = {Energy: 5000, Minerals: 2000}`。
- `/tmp/swarm-review-R24/specs/core/08-resource-ledger.md:125` 至 `/tmp/swarm-review-R24/specs/core/08-resource-ledger.md:127` 定义 `free_upkeep_controllers = 1`、`free_upkeep_drones = 3`、`free_upkeep_ticks = 2000`。
- `/tmp/swarm-review-R24/specs/core/08-resource-ledger.md:197` 至 `/tmp/swarm-review-R24/specs/core/08-resource-ledger.md:198` 将 `WorldStartupSubsidy` 放在资源执行顺序第 1 步，随后才是 `UpkeepDeduction`。
- `/tmp/swarm-review-R24/specs/reference/api-registry.md:480` 至 `/tmp/swarm-review-R24/specs/reference/api-registry.md:483` 在权威 registry 中同步了 starting resources 与 free upkeep 参数。

Closure assessment:
- 原 blocker 的架构风险是新玩家在 World 启动时先遇到 upkeep sink，缺少启动补贴/免维护导致经济不可存活。R24 通过一次性启动资源、免维护对象数量、免维护持续 tick、执行顺序和 identity-bound 反 smurf 约束闭合该风险。

[B3] CLOSED — 确定性合同已闭合。

Evidence:
- `/tmp/swarm-review-R24/specs/core/01-tick-protocol.md:620` 至 `/tmp/swarm-review-R24/specs/core/01-tick-protocol.md:623` 定义确定性合同：给定 tick N-1 状态、tick N RawCommand、world_seed、激活模组列表，`execute_deterministic == recorded_state`。
- `/tmp/swarm-review-R24/specs/core/01-tick-protocol.md:751` 至 `/tmp/swarm-review-R24/specs/core/01-tick-protocol.md:759` 定义完整 command sort key：`priority_class`、`shuffle_index`、`source_rank`、`sequence`、`command_hash`，并声明相同 seed/玩家集/命令集得到相同执行顺序。
- `/tmp/swarm-review-R24/specs/core/01-tick-protocol.md:441` 至 `/tmp/swarm-review-R24/specs/core/01-tick-protocol.md:444` 定义 FDB commit 失败重试时复用 canonical COLLECT buffer，不重新执行 WASM，避免重试分叉。
- `/tmp/swarm-review-R24/specs/core/06-phase2b-system-manifest.md:9` 至 `/tmp/swarm-review-R24/specs/core/06-phase2b-system-manifest.md:13` 定义 Phase 2a/2b 统一清单、serial spine + parallel sets、stable IDs、显式迭代顺序、R/W 声明。
- `/tmp/swarm-review-R24/specs/core/06-phase2b-system-manifest.md:185` 至 `/tmp/swarm-review-R24/specs/core/06-phase2b-system-manifest.md:190` 定义 special attack reducer 的 parallel collect → merge sort → reducer resolve → status advance 执行表。
- `/tmp/swarm-review-R24/specs/core/06-phase2b-system-manifest.md:216` 至 `/tmp/swarm-review-R24/specs/core/06-phase2b-system-manifest.md:231` 定义 Special Attack Unique Writer Contract 与 canonical `pending_intents`，禁止 nondeterministic push order。
- `/tmp/swarm-review-R24/specs/core/06-phase2b-system-manifest.md:380` 至 `/tmp/swarm-review-R24/specs/core/06-phase2b-system-manifest.md:388` 定义 CI 验证：R/W 冲突、并行安全、迭代确定性、manifest 一致性、SpawningGrace filter。

Closure assessment:
- 原 blocker 的架构风险是多个“合理实现”在排序、并发写入、重试、system order 上产生 replay 分叉。R24 已把排序键、重试缓存、system manifest、unique writer、并行安全和 CI 校验写成合同，闭合该类分叉风险。

[B4] CLOSED — 容量证明 + benchmark/回归合同已闭合。

Evidence:
- `/tmp/swarm-review-R24/design/engine.md:286` 定义性能合同为 deadline-driven hard contract，且全部指标在 CI 中回归测试。
- `/tmp/swarm-review-R24/design/engine.md:292` 至 `/tmp/swarm-review-R24/design/engine.md:298` 定义 World/Arena tick pipeline 预算：World tick interval 3000ms、SNAPSHOT ≤50ms p99、COLLECT ≤2500ms、EXECUTE ≤400ms、COMMIT ≤50ms p99、BROADCAST ≤50ms、per-player sandbox deadline 2500ms。
- `/tmp/swarm-review-R24/design/engine.md:304` 至 `/tmp/swarm-review-R24/design/engine.md:315` 定义单节点 World 容量合同：target 500 / hard cap 1000 active players、target 5000 / hard cap 10000 drones、50000 total entities、256KB WASM snapshot、100 commands/player/tick、100000 explored nodes/tick pathfinding budget。
- `/tmp/swarm-review-R24/design/engine.md:319` 至 `/tmp/swarm-review-R24/design/engine.md:335` 给出 aggregate CPU admission formula 与 `ERR_CPU_SATURATED` 准入策略。
- `/tmp/swarm-review-R24/design/engine.md:337` 至 `/tmp/swarm-review-R24/design/engine.md:360` 给出 worker pool 推导，包含默认 256、hard cap 1000、500/1000 active player 场景。
- `/tmp/swarm-review-R24/design/engine.md:362` 至 `/tmp/swarm-review-R24/design/engine.md:394` 给出 500 target 与 1000 hard cap 的容量推导、超限 `ERR_WORLD_FULL`、fair-share admission。
- `/tmp/swarm-review-R24/specs/reference/api-registry.md:456` 至 `/tmp/swarm-review-R24/specs/reference/api-registry.md:460` 声明全局容量限制是权威上限。
- `/tmp/swarm-review-R24/specs/reference/api-registry.md:468` 至 `/tmp/swarm-review-R24/specs/reference/api-registry.md:499` 同步游戏/WASM 限制，包括 per-player drone cap 50、per-room cap 500、global drone cap 10000、global entity cap 50000、sandbox CPU、deadline、pathfinding budget。
- `/tmp/swarm-review-R24/specs/reference/api-registry.md:520` 至 `/tmp/swarm-review-R24/specs/reference/api-registry.md:531` 定义硬件基线：500 target active players on 64GB RAM/32 cores、1000 hard cap、worker pool max/default/hard cap、degraded mode。
- `/tmp/swarm-review-R24/specs/reference/api-registry.md:533` 至 `/tmp/swarm-review-R24/specs/reference/api-registry.md:541` 定义 per-player fair-share admission。

Closure assessment:
- 原 blocker 的架构风险是容量数字没有可执行依据，容易成为愿望清单。R24 已补齐 deadline budget、硬上限、硬件基线、worker pool/admission 公式、CI 回归声明与 registry 权威容量表，足以作为架构 closure。

## Phase Ordering

1. B1 before implementation: World 启动经济参数必须先进入 world/economy config 与 Resource Ledger，再实现 upkeep/storage tax，否则新玩家路径会先被 sink 吃掉。
2. B3 before concurrency optimization: 必须先锁定 command sort key、system manifest、unique writer 与 replay envelope，再做 Bevy parallel set 或 worker retry 优化。
3. B4 before load expansion: 先以 registry §5 的 500 target / 1000 hard cap 与 engine §3.4 CI budget 建立 benchmark gate，再允许调大 `worker_pool_max` 或开放更高 active-player slot。
