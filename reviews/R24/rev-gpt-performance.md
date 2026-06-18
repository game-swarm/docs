# R24 Closure Verification — 性能评审 (GPT-5.5)

## Verdict
APPROVE

## Strengths
- B3 已闭合：WASM SIMD 默认禁用，relaxed SIMD 始终禁用；仅允许显式 opt-in 的 deterministic subset。
- B4 已闭合：容量合同、room partition、D6/B room-level cap 与 D2/B 三层 drone cap 已有权威参数与执行约束。
- Tick 关键路径的预算、worker pool、snapshot 分片、fair-share admission 均有硬性数字，可用于后续 CI/压测回归。

## Concerns
- P1: None for scoped closure items.
- P2: None for scoped closure items.

## Closure Verification

### [B3] CLOSED — SIMD 禁用
证据：
- `/tmp/swarm-review-R24/specs/core/04-wasm-sandbox.md:92` 明确禁用 WASM threads。
- `/tmp/swarm-review-R24/specs/core/04-wasm-sandbox.md:94` 配置 `config.wasm_simd(world_config.simd_enabled)`，并说明 SIMD 由 `world.toml` 控制、默认禁用，仅显式 opt-in `deterministic_subset` 时启用。
- `/tmp/swarm-review-R24/specs/core/04-wasm-sandbox.md:95` 明确 `config.wasm_relaxed_simd(false)`，relaxed SIMD 始终禁用。
- `/tmp/swarm-review-R24/design/engine.md:407` 在 Sandbox 生命周期中再次声明 WASI 默认关闭，并列出 threads、atomics、SIMD 默认禁用；deterministic integer subset 需跨架构验证后 opt-in。

闭合判断：满足 B3。默认路径无 SIMD/relaxed SIMD；启用路径被限制为显式、确定性子集，避免跨架构非确定性与 tick 性能不可控。

### [B4] CLOSED — 容量证明 + D6/B room-partition + D2/B drone cap
证据：
- 容量合同：`/tmp/swarm-review-R24/design/engine.md:288`-`/tmp/swarm-review-R24/design/engine.md:299` 给出 Tick Pipeline 硬预算：World tick interval 3000ms，SNAPSHOT ≤50ms p99，COLLECT ≤2500ms，EXECUTE ≤400ms，COMMIT ≤50ms p99，BROADCAST ≤50ms，per-player sandbox deadline 2500ms。
- 单节点容量：`/tmp/swarm-review-R24/design/engine.md:300`-`/tmp/swarm-review-R24/design/engine.md:315` 给出 target 500 / hard cap 1000 active players、target 5000 / hard cap 10000 active drones、total entities hard cap 50000、per-player drone cap 50、snapshot cap 256KB、commands/player/tick 100、pathfinding budget 100000 explored nodes/tick。
- 容量推导：`/tmp/swarm-review-R24/design/engine.md:319`-`/tmp/swarm-review-R24/design/engine.md:335` 给出 aggregate CPU admission formula 与 `MIN_FUEL=500000` admission gate；`/tmp/swarm-review-R24/design/engine.md:337`-`/tmp/swarm-review-R24/design/engine.md:360` 给出 worker pool 默认 256、hard cap 1000；`/tmp/swarm-review-R24/design/engine.md:362`-`/tmp/swarm-review-R24/design/engine.md:392` 给出 500/1000 players 推导与超过 hard cap 的 `ERR_WORLD_FULL` 拒绝策略。
- D6/B room-partition：`/tmp/swarm-review-R24/design/engine.md:188`-`/tmp/swarm-review-R24/design/engine.md:195` 描述 tick 开始一次性构建世界快照并按房间分片，玩家可见数据通过当前房间 + 相邻房间最多 9 个分片拼接；`/tmp/swarm-review-R24/design/engine.md:258` 明确复杂度从 `O(玩家数 × 实体数)` 降为 `O(实体数 + 玩家数 × 可见房间数)`。
- D2/B drone cap：`/tmp/swarm-review-R24/design/engine.md:75`-`/tmp/swarm-review-R24/design/engine.md:84` 定义 RCL 房间 drone 上限 50/100/200/300/400/500/500/500；`/tmp/swarm-review-R24/design/engine.md:307` 明确 per-room / per-player / per-world 三层取较小值；`/tmp/swarm-review-R24/specs/reference/api-registry.md:468`-`/tmp/swarm-review-R24/specs/reference/api-registry.md:472` 给出权威上限：per-player 50、per-room 500、global drone 10000、global entity 50000；`/tmp/swarm-review-R24/specs/reference/api-registry.md:132` 注册 `RoomDroneCapReached` 拒绝码。
- 权威容量源：`/tmp/swarm-review-R24/design/engine.md:396` 指向 `api-registry.md` §5 为容量上限和准入策略权威；`/tmp/swarm-review-R24/specs/reference/api-registry.md:456`-`/tmp/swarm-review-R24/specs/reference/api-registry.md:531` 覆盖游戏限制、WASM 限制与硬件基线；`/tmp/swarm-review-R24/specs/reference/api-registry.md:533`-`/tmp/swarm-review-R24/specs/reference/api-registry.md:542` 覆盖 per-player fair-share admission。

闭合判断：满足 B4。容量证明包含 500 target / 1000 hard cap 场景、worker pool 与 CPU/fuel admission；room-partition 将 snapshot 构建从 per-player full serialization 降为 room shard stitching；drone cap 同时覆盖 per-player、per-room、global 三层，并有 canonical rejection code。

## Bottleneck Analysis
- Tick 关键路径主瓶颈仍被显式限定在 COLLECT/WASM dispatch：World 模式 2500ms collect budget 与 2500ms per-player sandbox deadline 是主保护线。
- EXECUTE 被限制在 400ms，并通过 Phase 2a inline + Phase 2b manifest/parallel sets 管控依赖；本 CV 范围内无需新增依赖问题。
- FDB commit 预算为 ≤50ms p99，且 persistence contract 采用 FDB 小对象 + object store 异步 blob，降低 tick commit 热点和大 blob 事务风险。
- Snapshot room partition 是 B4 的关键性能闭合点：默认最多 9 个可见房间分片，避免 1000 玩家时重复全世界序列化。

## Throughput Estimates
- Target 500 active players：文档推导以 500 × 5ms avg = 2500ms 作为 collect 饱和点，属于安全操作点但 p99 会造成排队风险。
- Hard cap 1000 active players：依赖 1000 worker hard cap 与 fuel throttling，文档估算 dispatch/stitching overhead ≈500ms，剩余 ≈2000ms execution budget，即约 2ms/player 可用时间。
- Drone scale：global active drone hard cap 10000；1000 players × per-player cap 50 的理论上限被 global cap 截断，避免 50000 drone 级别进入 tick。
- Snapshot scale：per-player WASM snapshot 256KB，room shard stitching + truncation/fair-share admission 将 worst-case 输入和 host/pathfinding 开销封顶。
