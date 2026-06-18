# R24 Closure Verification — 安全评审 (GPT-5.5)

Verdict: APPROVE

## Scope

本轮仅验证 R23 共识项中安全方向范围内的闭合状态：B3（SIMD 禁用 + D5/A）与 B4（容量证明）。未进行开放式新问题审计，未纳入范围外发现。

## Verification

### [B3] CLOSED — SIMD 禁用 + D5/A 已闭合

证据：

- `specs/core/04-wasm-sandbox.md:92`–`95` 在 Wasmtime 配置中明确 `wasm_threads(false)`、`wasm_simd(world_config.simd_enabled)`，并声明 SIMD 默认禁用，仅在 `world.toml` 显式 opt-in `deterministic_subset` 时启用；`wasm_relaxed_simd(false)` 始终禁用 relaxed SIMD。
- `design/engine.md:402`–`410` 的 Sandbox 生命周期条款再次要求 per-tick clean Store/Instance reset、WASI 默认关闭，并列出 threads、atomics、SIMD 默认禁用；允许 opt-in 的 SIMD 仅限 deterministic integer subset，且需要跨架构验证。
- `specs/core/04-wasm-sandbox.md:294`–`307` 给出 D5/A 相关执行期资源预算总表：fuel 10,000,000、WASM 线性内存 64MB、进程总内存 128MB、墙钟 2500ms、模块体积 5MB、host function/path_find/get_objects_in_range/output JSON 上限均有明确限制。
- `specs/core/04-wasm-sandbox.md:336`–`346` 给出编译期预算：编译超时 30s、编译内存 512MB、部署独立 fork、并发编译最多 5 个、module validation 10ms。
- `specs/core/04-wasm-sandbox.md:347`–`357` 明确 Query Host Function 单次调用成本，特别是 `host_path_find` 按实际工作量计费并有 per-player/per-tick 上限与全局 explored nodes 额度。

结论：B3 所要求的 SIMD 默认禁用、relaxed SIMD 禁止、deterministic opt-in 边界，以及 D5/A 所需的执行期/编译期/host function 资源限制均已在允许文档中闭合。

### [B4] CLOSED — 容量证明已闭合

证据：

- `design/engine.md:284`–`299` 定义 deadline-driven Tick Pipeline 预算：World tick interval 3000ms，SNAPSHOT ≤50ms p99，COLLECT ≤2500ms，EXECUTE ≤400ms，COMMIT ≤50ms p99，BROADCAST ≤50ms，per-player sandbox deadline 2500ms。
- `design/engine.md:300`–`316` 定义单节点 World 模式容量合同：active players target 500 / hard cap 1000，active drones target 5000 / hard cap 10000，total entities hard cap 50000，per-player snapshot 256KB，commands/pathfinding 等请求上限齐全。
- `design/engine.md:319`–`335` 给出 aggregate CPU admission formula，基于 COLLECT budget、CPU cores、PER_CORE_MIPS 与 MAX_FUEL 推导 per-player quota，并在低于 MIN_FUEL 时拒绝新玩家 WASM 执行。
- `design/engine.md:337`–`360` 给出 worker pool 推导，覆盖 256 worker default scenario 与 1000 worker hard cap scenario，并要求 operator 显式启用超默认容量。
- `design/engine.md:362`–`394` 给出 500/1000 player capacity derivation 与 per-player fair-share admission，解释 target 500 与 hard cap 1000 的前提、风险和拒绝策略。
- `specs/core/05-persistence-contract.md:340`–`388` 补充 room-partition FDB 事务策略与 synthetic benchmark gate：100k commands/tick validate/apply、50k entity snapshot clone/restore、FDB single-tx 500 active players、FDB room-partition 1000 active players/200 rooms、pathfinding 与 rollback benchmark 均有 p99 判定标准；明确 gate 失败则容量声明不可信。

结论：B4 要求的容量证明已从 tick budget、资源上限、CPU admission、worker pool、500/1000 player 推导、room-partition 事务策略与 benchmark gate 多层闭合。容量声明不再只是口头目标，而有可验证的判定标准。

## Final Verdict

APPROVE — 本轮安全方向待验证项 B3 与 B4 均为 CLOSED。