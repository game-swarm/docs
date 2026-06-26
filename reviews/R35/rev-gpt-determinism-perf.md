# R35 Determinism & Performance Review — GPT-5.5

## 1. Verdict

REQUEST_MAJOR_CHANGES

设计已覆盖大量确定性与性能关键点（seeded shuffle、canonical JSON、固定点数、Phase 2b manifest、WASM fuel metering、shadow write 等），但仍存在几处会直接导致实现者分叉或 replay/线上 tick 语义冲突的问题。尤其是 TickCommitRecord 字段权威定义在 `api-registry`、`engine`、`tick-protocol`、`persistence-contract` 之间不一致；WASM fuel/cgroup CPU 口径与容量推导互相矛盾；Phase 2a/Phase 2b 的 HitPoints 写入合同与调度 manifest 内部冲突。这些都属于确定性与性能方向的阻塞问题。

## 2. 发现的问题

### DNP-1 — High — TickCommitRecord / TickTrace replay-critical 字段集合在多个权威文档中不一致

- 位置：`/tmp/swarm-review-R35/specs/core/05-persistence-contract.md:34`、`/tmp/swarm-review-R35/specs/core/05-persistence-contract.md:36`、`/tmp/swarm-review-R35/specs/core/05-persistence-contract.md:43`、`/tmp/swarm-review-R35/specs/core/05-persistence-contract.md:302`、`/tmp/swarm-review-R35/specs/reference/api-registry.md:657`、`/tmp/swarm-review-R35/specs/reference/api-registry.md:659`、`/tmp/swarm-review-R35/design/engine.md:271`
- 问题描述：`05-persistence-contract.md` §2.1 声称 TickCommitRecord 由 10 个 replay-critical 字段组成，但同文件 §7.1 又给出含 `collect_id`、`attempt_id`、`commit_id`、`wasm_status`、`fuel_ledger`、`system_manifest_hash` 等字段的 TickCommitRecord 扩展结构；`api-registry.md` §6 另称 TickInputEnvelope 共 22 个字段；`engine.md` §3.3 又列出包含 `deploy_events`、`rollback_events`、`admin_events`、`terminal_state` 等的封套。更严重的是 `engine.md` 说 `fuel_schedule_version`、`host_cost_table_version` 写入 TickCommitRecord，而 10 字段权威表没有这些字段。
- 影响分析：实现者无法判断 replay verifier 的最小输入到底是 10 字段、扩展 TickCommitRecord、还是 22 字段 TickTrace Envelope。不同节点若选择不同字段参与 `state_checksum`、`commands_hash`、`commit_id` 或 `manifest_hash`，会出现线上 tick 与 replay hash 分叉；审计系统也无法稳定区分 `audit_gap`、`reconstructable` 与 `unreplayable`。
- 修复建议：建立一个唯一机器权威的 `TickCommitRecord` schema，并在三个文档中统一引用，不再重列冲突表。建议将 `api-registry.md` 的 TickTrace Envelope 拆为：`TickCommitRecord`（FDB same-tx replay-critical）、`TickInputEnvelope`（WASM/collect 输入诊断）、`RichTraceBlob`（debug async）三张表，并明确每个字段的存储位置、是否参与 hash chain、是否 replay-required。`05-persistence-contract.md` §2.1 的“10 个字段”需与 §7.1 和 `engine.md` §3.3 合并为同一清单；若 `fuel_schedule_version`/`host_cost_table_version` 影响 fuel replay，就必须进入 replay-critical 字段。

### DNP-2 — High — WASM fuel、wall-clock deadline、cgroup CPU 与容量推导口径互相矛盾

- 位置：`/tmp/swarm-review-R35/design/README.md:43`、`/tmp/swarm-review-R35/design/README.md:54`、`/tmp/swarm-review-R35/design/engine.md:321`、`/tmp/swarm-review-R35/design/engine.md:326`、`/tmp/swarm-review-R35/design/engine.md:334`、`/tmp/swarm-review-R35/design/engine.md:338`、`/tmp/swarm-review-R35/design/engine.md:371`、`/tmp/swarm-review-R35/specs/core/04-wasm-sandbox.md:269`、`/tmp/swarm-review-R35/specs/core/04-wasm-sandbox.md:271`、`/tmp/swarm-review-R35/specs/reference/api-registry.md:570`
- 问题描述：设计原则把 CPU 配额描述为“指令计数 / fuel metering”，`engine.md` 又承认 fuel 是 Wasmtime fuel units、不同版本/配置不可直接比较；容量公式使用 `PER_CORE_FUEL_RATE` 和 2500ms 推导每玩家 quota，但 `04-wasm-sandbox.md`/`api-registry.md` 同时给每个 sandbox cgroup `cpu.max = 250000 3000000`（每 3s 仅 0.25 CPU 秒），且 `engine.md` 又允许每玩家 sandbox deadline 2500ms。1000 worker 并行时，如果每个 worker 都拥有 0.25 CPU 秒/3s，理论 CPU 需求会远超单节点 32/40 cores；如果 cgroup 是全 sandbox 池共享，则文档没有说明层级，per-player deadline 与 fuel quota 又无法直接推导。
- 影响分析：这是性能合同与公平合同的核心矛盾。按当前文字实现，运营方可能按 per-worker cgroup 配额导致 CPU 超卖，或按全局 cgroup 配额导致每玩家 2500ms deadline 形同虚设；不同硬件上的 fuel-to-time 映射也会让“同等算力”承诺失真。Replay 可记录 fuel 消耗，但容量 admission、Overload 削减、refund、fair-share 都依赖同一个 fuel 口径，若口径不统一会出现策略不可解释甚至可被利用。
- 修复建议：明确三层资源口径并统一命名：`wasmtime_fuel_units`（确定性计费）、`sandbox_wall_deadline_ms`（防 hang）、`cpu_cgroup_quota`（OS 防 DoS）。容量公式不得把 Wasmtime fuel 等同真实 CPU instructions；应以基准校准表 `fuel_schedule_version -> calibrated_fuel_per_core_ms` 为 admission 输入，并写入 replay-critical manifest。明确 cgroup 是 per-worker 还是 sandbox pool 级；若 per-worker，则 hard cap 与 worker_pool_max 必须受 `CPU_CORES × tick_interval / cpu.max` 约束；若 pool 级，则表格应改为 pool cgroup，而非每 sandbox worker。

### DNP-3 — High — HitPoints / HP 修改路径与“unique writer”合同冲突，Phase 2a 仍声明直接写 hits

- 位置：`/tmp/swarm-review-R35/design/engine.md:245`、`/tmp/swarm-review-R35/design/engine.md:247`、`/tmp/swarm-review-R35/specs/core/06-phase2b-system-manifest.md:92`、`/tmp/swarm-review-R35/specs/core/06-phase2b-system-manifest.md:97`、`/tmp/swarm-review-R35/specs/core/06-phase2b-system-manifest.md:190`、`/tmp/swarm-review-R35/specs/core/06-phase2b-system-manifest.md:210`、`/tmp/swarm-review-R35/specs/core/06-phase2b-system-manifest.md:212`、`/tmp/swarm-review-R35/specs/core/06-phase2b-system-manifest.md:217`、`/tmp/swarm-review-R35/specs/core/06-phase2b-system-manifest.md:246`、`/tmp/swarm-review-R35/specs/core/06-phase2b-system-manifest.md:411`
- 问题描述：`engine.md` 明确 Attack/RangedAttack/Heal 在 Phase 2a 只生成 `PendingDamage`/`PendingHeal`，不直接修改 HP；但 manifest 的 S01 `command_executor` `Writes` 包含 `Entity (hits)`，R/W 矩阵也标记 S01 写 `HitPoints`。同一 manifest 又称 S15 是 combat damage + heal 的 unique HitPoints writer，但随后承认 S10 regen、S22 status_advance_system、S24 decay 也写 HitPoints，并把“unique writer”降级为“domain-specific writer”。此外 S22 的职责既写 StatusState，又直接写 Entity hits/armor/resource/fuel，和“StatusState 唯一 writer”及“HP 统一结算”叙述混在一起。
- 影响分析：这是 ECS 调度确定性的关键合同。若实现者按 S01 写 hits，Phase 2a command order 会影响 HP；若按 S15 统一写，则 S01 的 R/W 矩阵错误会导致 CI 并行安全验证误报/漏报。S22/S24 对 HitPoints 的写入也需要明确与 S15 的顺序、过滤条件和 effect domain，否则特殊攻击、decay、death_mark 在同 tick 内可能产生重复伤害、死后继续修改或 replay 分叉。
- 修复建议：把 HitPoints 写入合同拆成显式 component/buffer：`PendingDamage`、`PendingHeal`、`PendingStatusEffect`、`HitPoints`。S01 对 Attack/Heal 只能写 pending buffer，不得写 `HitPoints`；S15 是 combat/heal HitPoints writer；S22 若确实会改 HP（Leech 等），需定义为 `StatusEffectDamageBuffer -> S15`，或明确 S22 是独立 HP writer 并给出严格顺序与 `Without<DeathMark>`/`Without<SpawningGrace>` 过滤。R/W 矩阵必须与文字一致，CI gate 应检查同一 semantic domain 的唯一 writer，而不是用“domain-specific”注解绕开冲突。

### DNP-4 — Medium — RNG seed 派生公式在 design 与 spec 中不一致，且 `host_get_random` ABI 参数类型不一致

- 位置：`/tmp/swarm-review-R35/design/engine.md:268`、`/tmp/swarm-review-R35/specs/core/01-tick-protocol.md:235`、`/tmp/swarm-review-R35/specs/core/01-tick-protocol.md:238`、`/tmp/swarm-review-R35/specs/core/01-tick-protocol.md:881`、`/tmp/swarm-review-R35/specs/core/04-wasm-sandbox.md:221`、`/tmp/swarm-review-R35/specs/reference/api-registry.md:474`
- 问题描述：`engine.md` 使用 `Blake3("shuffle" || world_seed || tick.to_le_bytes())`；`01-tick-protocol.md` §3.1 示例却写 `Blake3(tick_number || world_seed)`，同文 §9.1 又回到带 domain separator 的公式。`04-wasm-sandbox.md` 的 `host_get_random` 签名为 `sequence: u32`，`api-registry.md` 权威签名为 `sequence: u64`。RNG namespace 表也写 `world_seed + tick` 这种非规范串接表达。
- 影响分析：RNG 合同必须直观且单一。seed 拼接顺序、domain separator、整数宽度任何一处不一致都会导致 shuffle、combat RNG、host random 在 replay 中分叉。`sequence` u32/u64 ABI 不一致还会造成 SDK 与 host import signature 不匹配，轻则部署失败，重则跨语言截断导致随机流碰撞。
- 修复建议：定义统一 `derive_rng(domain: ascii, world_seed: [u8;32], tick: u64, actor/entity/source: optional, sequence: u64) -> Blake3 XOF` 规范，所有文档只引用此函数，不写临时公式。将 `host_get_random` 全部统一为 `u64 sequence` 或明确选择 `u32` 并更新 registry；鉴于 registry 是 API 权威，建议改 `04-wasm-sandbox.md` 为 u64。所有示例必须包含 domain separator 和 length-delimited encoding，避免 `a||bc`/`ab||c` 歧义。

### DNP-5 — Medium — 容量上限与性能合同存在目标/硬值语义混乱

- 位置：`/tmp/swarm-review-R35/design/engine.md:288`、`/tmp/swarm-review-R35/design/engine.md:302`、`/tmp/swarm-review-R35/design/engine.md:306`、`/tmp/swarm-review-R35/design/engine.md:410`、`/tmp/swarm-review-R35/specs/reference/api-registry.md:532`、`/tmp/swarm-review-R35/specs/reference/api-registry.md:534`、`/tmp/swarm-review-R35/specs/reference/api-registry.md:602`、`/tmp/swarm-review-R35/specs/reference/api-registry.md:603`
- 问题描述：`engine.md` 称 §3.4 是 “deadline-driven 硬性能合同，全部指标在 CI 中回归测试”，并把 active players target 500 / hard cap 1000、active drones hard cap 10000 写入容量合同；但 `api-registry.md` 的权威容量表又说 target 500 “实际容量由压力测试确定——tick 时间可随负载弹性增加”，hard cap 1000 “benchmark-gated（未验证）”。这使“硬性能合同”与“benchmark-gated 未验证”同时存在。
- 影响分析：容量 admission、degraded mode、worker pool sizing、tick overrun policy 依赖这些数字。如果 1000 是未验证 benchmark gate，就不应作为硬 cap 的设计事实；如果是硬 cap，则必须有明确的拒绝/降级语义和 CI benchmark gate。当前措辞会让实现和运维对 SLO/SLA 产生不同解释。
- 修复建议：把容量项拆为三类：`design_limit`（协议上限，如 command 100、snapshot 256KB）、`admission_default`（默认运营阈值，如 target 500）、`benchmark_claim`（需硬件基线验证的性能声明）。`engine.md` 可保留预算合同，但引用 `api-registry.md` 的权威硬上限；`api-registry.md` 若称 benchmark-gated，必须定义 gate 失败时的目标状态（例如降低 admission_default，而非改变协议上限）。

### DNP-6 — Medium — Shadow Write / GlobalTickCommit 描述疑似超出 FDB 单事务能力边界，需要澄清实现语义

- 位置：`/tmp/swarm-review-R35/specs/core/01-tick-protocol.md:427`、`/tmp/swarm-review-R35/specs/core/01-tick-protocol.md:431`、`/tmp/swarm-review-R35/specs/core/01-tick-protocol.md:435`、`/tmp/swarm-review-R35/specs/core/01-tick-protocol.md:439`、`/tmp/swarm-review-R35/specs/core/05-persistence-contract.md:367`、`/tmp/swarm-review-R35/specs/core/05-persistence-contract.md:388`
- 问题描述：文档要求 GlobalTickCommit 在一个 FDB 原子事务中读取 staging 行并将其“原子提升”为 `/committed/` 路径，且 staging 行仅 GlobalTickCommit 在同一事务中读取。若 staging 行总量随 room 数增加，这个事务可能需要读取/写入所有房间 pointer/hash，甚至执行大量 key promotion。文档同时要求 room-partition 用于 1000 players / 200 rooms，并宣称每 room staging <2KB，但没有定义 promotion 是复制数据、pointer swap、版本戳索引，还是 manifest-only publish。
- 影响分析：如果实现为复制 staging state 到 committed，GlobalTickCommit 事务会重新聚合大量数据，可能超过 FDB 事务大小/冲突预算，成为 tick 瓶颈；如果实现为 manifest pointer publish，则“staging 行仅 GlobalTickCommit 在同一事务中读取”和“promotion 删除/提升”语义应改写。当前合同太像目标语义而非可验证的数据布局，会导致性能实现分叉。
- 修复建议：明确采用 manifest-only publish：per-room staging 事务写不可见 content-addressed rows；GlobalTickCommit 只写 global head、room hash list、staging namespace epoch pointer，不复制 room state。读路径通过 committed manifest 指向 staging/object rows，GC 只在 manifest 未引用时清理。给出 GlobalTickCommit 最大写入字节、read conflict range、write conflict range 与 200 rooms 下 p99 预算。

### DNP-7 — Low — `canonical_json` 与 RFC 8785/JCS 规则表述不完全一致，可能误导 SDK 实现

- 位置：`/tmp/swarm-review-R35/specs/core/01-tick-protocol.md:757`、`/tmp/swarm-review-R35/specs/core/02-command-validation.md:99`
- 问题描述：`01-tick-protocol.md` 指定 RFC 8785 JCS，并禁止浮点 JSON 数字；`02-command-validation.md` 对 `canonical_json()` 的摘要写“键排序、无空格、数值无尾零、字符串 NFC 归一化”。JCS 对字符串并不要求 Unicode NFC 归一化；它要求保留 Unicode 字符串数据并按 ES6 JSON 序列化规则生成。额外引入 NFC 会改变玩家提交字符串的字节语义。
- 影响分析：如果 Rust/Go/TS SDK 有的执行 NFC、有的不执行，`command_hash` 和签名 payload 会分叉。虽然游戏状态禁用浮点降低了主要风险，但 canonical command hash 是排序 tiebreaker，必须跨语言完全一致。
- 修复建议：以 RFC 8785/JCS 为唯一 canonical JSON 规则，并显式说明“不做 Unicode normalization；输入层如需限制玩家名字符集，在 schema validation 中完成”。若项目确实想做 NFC，必须定义为 JCS 前的独立 normalization pass，并进入 `canonical_codec_version`。

## 3. 亮点

- 确定性核心意识很强：`BTreeMap`/`IndexMap` 使用边界、禁止 `std::HashMap` 迭代、禁用 float、定点整数与 floor 舍入规则都已明确，见 `design/engine.md:264`–`design/engine.md:270` 与 `design/engine.md:469`–`design/engine.md:475`。
- 命令排序兼顾公平与 replay：seeded shuffle、PlayerId canonical sort、rejection sampling 消除 modulo bias、`command_hash` tiebreaker 的方向正确，见 `specs/core/01-tick-protocol.md:232`–`specs/core/01-tick-protocol.md:255` 与 `specs/core/01-tick-protocol.md:871`–`specs/core/01-tick-protocol.md:889`。
- Tick 原子性目标清晰：shadow write + atomic publish 解决了 per-room partial commit 的历史陷阱，且明确 Broadcast failure 不回滚 committed tick，见 `specs/core/01-tick-protocol.md:398`–`specs/core/01-tick-protocol.md:409` 与 `specs/core/01-tick-protocol.md:612`–`specs/core/01-tick-protocol.md:624`。
- WASM 沙箱的隔离层次完整：Wasmtime fuel、epoch interruption、Store reset、禁 WASI clock/random/fs/network、seccomp/cgroup/netns 多层防护覆盖面较好，见 `specs/core/04-wasm-sandbox.md:41`–`specs/core/04-wasm-sandbox.md:55`、`specs/core/04-wasm-sandbox.md:75`–`specs/core/04-wasm-sandbox.md:109`、`specs/core/04-wasm-sandbox.md:111`–`specs/core/04-wasm-sandbox.md:130`。
- 快照与输出截断处理选择了确定性语义：snapshot truncation 使用 stable entity sort，WASM output 超限整批丢弃，避免部分解析造成状态不一致，见 `design/engine.md:426`–`design/engine.md:442` 与 `specs/core/01-tick-protocol.md:998`–`specs/core/01-tick-protocol.md:1009`。
- Phase 2b manifest 的方向正确：显式 system id、manifest hash、R/W matrix、parallel set、typed buffer、S22 serial committer 是可验证调度合同的正确形式，见 `specs/core/06-phase2b-system-manifest.md:9`–`specs/core/06-phase2b-system-manifest.md:17` 与 `specs/core/06-phase2b-system-manifest.md:461`–`specs/core/06-phase2b-system-manifest.md:472`。

## 4. CrossCheck — 需要跨方向检查

- CX1: `api-registry.md` 声称由 IDL 自动生成，但多个 spec 对 registry 中的字段、限制、函数签名有再声明和冲突 → 建议 API/IDL 方向检查 IDL 是否真的包含 TickCommitRecord、Host Function ABI、limits manifest 的唯一机器源，并建立 CI diff gate。
- CX2: Shadow Write 的 GlobalTickCommit 需要具体 FDB key layout、transaction conflict range 与 object-store pointer 语义 → 建议 Persistence/Storage 方向检查是否符合 FDB 事务大小、conflict range、versionstamp、GC 可达性约束。
- CX3: `host_get_random` 暴露确定性随机给玩家，且 Arena/World seed 披露策略不同 → 建议 Security/Anti-cheat 方向检查玩家能否通过 repeated `host_get_random(sequence)`、snapshot seed metadata 或 TickTrace 推断未来 shuffle/combat RNG。
- CX4: 特殊攻击（Overload、Leech、Fabricate）对 fuel、age、body/resource 的写入跨越 gameplay/economy/performance 边界 → 建议 Gameplay/Balance 方向检查这些效果是否应进入统一 resource ledger / status effect damage pipeline，而不是由 S22 直接多域写入。
- CX5: canonical JSON 与玩家名/字符串 normalization 牵涉 SDK、签名、prompt injection delimiter → 建议 Interface/SDK/Security 方向检查 JCS、schema validation、request signing canonical payload 是否使用同一 codec version。
