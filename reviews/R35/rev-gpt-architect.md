# R35 Architect Review — GPT-5.5

## 1. Verdict

REQUEST_MAJOR_CHANGES

理由：整体架构方向（WASM deferred command、ECS manifest、FDB replay-critical 分层、room-partition shadow write）是合理的，但当前文档在几个核心边界上仍存在会导致实现分叉的结构性冲突：Phase 2a/2b 的写入责任未闭合、special attack 在 core CommandAction 与 CustomActionRegistry 之间双重建模、replay-critical 与对象存储恢复路径互相矛盾、sandbox CPU 资源模型与 tick admission 预算不一致。这些不是数值微调，而是跨模块数据流与权威源边界问题，必须修复后才能进入可实现合同。

## 2. 发现的问题

### A1 — High — Phase 2a `command_executor` 仍声明直接写 HP，破坏 Phase 2b combat 归并边界

位置：
- `/tmp/swarm-review-R35/design/engine.md:245`
- `/tmp/swarm-review-R35/design/engine.md:247`
- `/tmp/swarm-review-R35/specs/core/06-phase2b-system-manifest.md:92`
- `/tmp/swarm-review-R35/specs/core/06-phase2b-system-manifest.md:95`
- `/tmp/swarm-review-R35/specs/core/06-phase2b-system-manifest.md:97`
- `/tmp/swarm-review-R35/specs/core/06-phase2b-system-manifest.md:210`
- `/tmp/swarm-review-R35/specs/core/06-phase2b-system-manifest.md:217`
- `/tmp/swarm-review-R35/specs/core/06-phase2b-system-manifest.md:394`

问题描述：
`engine.md` 明确要求 Phase 2a Attack/RangedAttack/Heal 只生成 `PendingDamage`/`PendingHeal` intent，不直接修改目标 HP；Phase 2b S15 `damage_application` 是 combat damage/heal 的归并写入点。但 manifest 的 S01 `command_executor` 同时处理 `Attack`、`RangedAttack`、`Heal`，并声明 `Writes: Entity (hits)`；R/W 矩阵也标记 S01 对 `HitPoints` 为 `W`。这使 Phase 2a 是否可直接改 HP 产生双重解释。

影响分析：
- 实现者可能在 S01 直接扣血，又在 S11-S15 归并扣血，产生 double-apply。
- `S15 UNIQUE HitPoints writer` 的语义被 S01 破坏，CI R/W 静态检查无法作为架构约束。
- Replay 中相同 command 在不同实现路径下会产生不同 HP 序列，破坏 determinism contract。

修复建议：
- 将 S01 的 Attack/RangedAttack/Heal 责任改为“validate + emit combat intent/sub-buffer”，不得写 `Entity.hits`。
- Manifest §S01 `Writes` 与 R/W matrix 中 S01 的 `HitPoints` 列改为不写；若 Move/Harvest 等确需写其他实体字段，拆分为更精确列，不用泛化 `Entity (hits)`。
- 将 S15 的 unique writer 合同表述为：combat/heal HP 只由 S15 写；S10 regen、S22 status effect 若仍写 HP，必须在矩阵和 CI 规则中明确为不同 semantic writer，而不是笼统 “unique writer”。

### A2 — High — Special attack 同时被建模为核心 CommandAction 与 CustomAction，扩展层边界不清

位置：
- `/tmp/swarm-review-R35/specs/reference/api-registry.md:37`
- `/tmp/swarm-review-R35/specs/reference/api-registry.md:43`
- `/tmp/swarm-review-R35/specs/reference/api-registry.md:48`
- `/tmp/swarm-review-R35/specs/reference/api-registry.md:75`
- `/tmp/swarm-review-R35/specs/reference/api-registry.md:79`
- `/tmp/swarm-review-R35/specs/reference/api-registry.md:81`
- `/tmp/swarm-review-R35/specs/core/06-phase2b-system-manifest.md:95`
- `/tmp/swarm-review-R35/specs/core/02-command-validation.md:667`
- `/tmp/swarm-review-R35/specs/core/02-command-validation.md:714`
- `/tmp/swarm-review-R35/specs/core/02-command-validation.md:810`
- `/tmp/swarm-review-R35/specs/core/02-command-validation.md:824`

问题描述：
API Registry 声明 CommandAction 总数为 21，且所有 21 个变体都包含 `object_id`；同时 §1.3 又说 8 个特殊攻击“通过 `CommandAction::Custom(type)` 路由至 `CustomActionRegistry`”。Manifest S01 则把 `Hack/Drain/.../Leech/Fabricate` 当作直接 handled commands。Command validation 后半部分又把 Leech/Fabricate 标为 `[[custom_actions]]` 注册方式。结果是同一 action 在 wire enum、custom registry、manifest handler 三处均有一等身份。

影响分析：
- SDK/codegen 无法直观判断 `Hack` 是 enum variant、custom action string，还是两者兼容别名。
- `world_action_manifest_hash` 与 `api_version` 的职责重叠：核心 action 变更应进 IDL，custom action 变更应进 manifest；当前 special attack 同时占用两条路径。
- `Standard/Arena 全量启用 8 种核心目标设计` 与 `CustomActionRegistry 扩展` 的抽象层次冲突，容易让实现出现“核心 hardcode + manifest override”双路径。

修复建议：
- 明确二选一：
  - 方案 A：8 种 special attack 全部作为 core CommandAction enum，删除 `CommandAction::Custom(type)` 路由说法；CustomActionRegistry 仅用于第三方/world mod 扩展。
  - 方案 B：core CommandAction 只保留 `CustomAction { type, payload }`，8 种 vanilla special attack 也由 World Action Manifest 注册，并由 IDL 生成 typed SDK wrapper。
- 结合当前“8 种全部核心目标设计”的目标，建议采用方案 A，保留 World Action Manifest 记录启用/参数/handler hash，但不把核心 special attack 伪装成 custom action。
- 同步修改 API Registry、Command Validation、Phase2b Manifest 中的术语：`core special attack` 与 `custom action` 不得混用。

### A3 — High — Persistence 文档中 deterministic replay 是否依赖对象存储存在直接矛盾

位置：
- `/tmp/swarm-review-R35/specs/core/05-persistence-contract.md:38`
- `/tmp/swarm-review-R35/specs/core/05-persistence-contract.md:39`
- `/tmp/swarm-review-R35/specs/core/05-persistence-contract.md:40`
- `/tmp/swarm-review-R35/specs/core/05-persistence-contract.md:58`
- `/tmp/swarm-review-R35/specs/core/05-persistence-contract.md:60`
- `/tmp/swarm-review-R35/specs/core/05-persistence-contract.md:217`
- `/tmp/swarm-review-R35/specs/core/05-persistence-contract.md:219`
- `/tmp/swarm-review-R35/specs/core/05-persistence-contract.md:222`
- `/tmp/swarm-review-R35/specs/core/05-persistence-contract.md:224`
- `/tmp/swarm-review-R35/specs/core/05-persistence-contract.md:320`
- `/tmp/swarm-review-R35/specs/core/05-persistence-contract.md:327`
- `/tmp/swarm-review-R35/specs/core/05-persistence-contract.md:328`

问题描述：
§2 明确声明 deterministic replay 只需要 FDB TickCommitRecord 10 字段 + keyframe/delta chain，对象存储中的任何数据都不是 replay 必需；Object Store 缺失只导致 `audit_gap`。但 §5.1 “正常 Replay” 又要求从对象存储获取 `tick_trace_blob`、验证 hash、反序列化 TickCommitRecord。§7.2 又把 RichTraceBlob 损坏分为 `audit_gap` / `unreplayable`，其中前后 keyframe 不可用会导致 `unreplayable`。这与 “对象存储缺失绝不 unreplayable” 冲突。

影响分析：
- Replay verifier 的输入源不清：到底从 FDB 的 TickCommitRecord 重放，还是从对象存储 tick_trace_blob 反序列化。
- `terminal_state = unreplayable` 的触发条件不稳定，可能把 rich debug blob 缺失误判为 replay-critical 丢失。
- FDB/Object Store 分层边界被破坏，后续实现容易重新滑向“blob 是 replay 必需”的双写耦合。

修复建议：
- 将 replay 流程拆成两个显式路径：
  - `deterministic_replay`: FDB TickCommitRecord + FDB/keyframe/delta chain；不读 RichTraceBlob。
  - `rich_debug_replay`: 在 deterministic replay 验证后，可选读取 RichTraceBlob；失败只标记 `audit_gap`。
- 修改 §5.1：不要把 `tick_trace_blob` 作为正常 deterministic replay 的前置步骤。
- 修改 §7.2：`unreplayable` 只能由 FDB replay-critical 字段或 keyframe/delta chain 缺失触发；RichTraceBlob 损坏不得单独触发 `unreplayable`。

### A4 — High — Sandbox CPU cgroup 合同与 tick admission/fuel 预算模型不一致

位置：
- `/tmp/swarm-review-R35/design/engine.md:321`
- `/tmp/swarm-review-R35/design/engine.md:326`
- `/tmp/swarm-review-R35/design/engine.md:332`
- `/tmp/swarm-review-R35/design/engine.md:334`
- `/tmp/swarm-review-R35/design/engine.md:371`
- `/tmp/swarm-review-R35/specs/core/04-wasm-sandbox.md:268`
- `/tmp/swarm-review-R35/specs/core/04-wasm-sandbox.md:271`
- `/tmp/swarm-review-R35/specs/core/04-wasm-sandbox.md:317`
- `/tmp/swarm-review-R35/specs/core/04-wasm-sandbox.md:320`
- `/tmp/swarm-review-R35/specs/core/04-wasm-sandbox.md:448`
- `/tmp/swarm-review-R35/specs/reference/api-registry.md:570`
- `/tmp/swarm-review-R35/specs/reference/api-registry.md:571`

问题描述：
Engine 的 aggregate CPU admission 用 `TICK_BUDGET_COLLECT_MS × CPU_CORES × PER_CORE_FUEL_RATE` 计算全局 fuel，且 per-player sandbox deadline 是 2500ms；但 sandbox cgroup 固定为 `cpu.max = 250000 3000000`，即每 3s 周期仅 0.25 CPU 秒。API Registry 也把 Sandbox CPU 固化为同一值。这里混淆了 wall-clock deadline、wasmtime fuel、Linux CFS CPU quota 三种资源。一个 CPU-bound WASM worker 即使 wall-clock 允许 2500ms，也可能在 250ms CPU 后被 throttled，导致实际 fuel/时间预算与 admission formula 不匹配。

影响分析：
- 玩家体验与计费不可预测：同样 10M fuel 在不同 cgroup throttling 状态下可能无法执行完。
- 容量推导中的 500/1000 active players 与 per-worker CPU quota 之间没有统一公式，运营者无法直观配置 worker pool。
- replay 不受 wall-clock 重跑影响，但 live tick 的 timeout/fuel_exhausted 分类会因 cgroup throttle 产生歧义。

修复建议：
- 建立单一资源预算模型：明确 `fuel` 是计费合同，`wall-clock deadline` 是故障隔离合同，`cgroup cpu.max` 是宿主保护合同。
- 将 cgroup CPU quota 从固定常量改为由 `per_player_cpu_quota` 或 `MAX_FUEL / PER_CORE_FUEL_RATE` 推导，并写入 `limits_manifest_hash`。
- 明确 throttling 语义：若 cgroup throttle 导致 wall-clock timeout，应归类为 `TimeoutExceeded` 还是 `ServerOverloaded`，并说明是否退还 fuel。

### A5 — Medium — Tick snapshot 架构在 design 与 spec 中仍同时呈现“全局分片一次构建”和“per-player visibility_filter(all_entities)”两种模型

位置：
- `/tmp/swarm-review-R35/design/engine.md:258`
- `/tmp/swarm-review-R35/specs/core/01-tick-protocol.md:141`
- `/tmp/swarm-review-R35/specs/core/01-tick-protocol.md:144`
- `/tmp/swarm-review-R35/specs/core/01-tick-protocol.md:145`
- `/tmp/swarm-review-R35/specs/core/01-tick-protocol.md:162`
- `/tmp/swarm-review-R35/specs/core/01-tick-protocol.md:176`
- `/tmp/swarm-review-R35/specs/core/01-tick-protocol.md:181`
- `/tmp/swarm-review-R35/specs/core/01-tick-protocol.md:183`

问题描述：
`engine.md` 描述两阶段快照架构：tick 开始一次性构建完整世界快照，按房间分片；玩家只拼接可见房间分片，复杂度为 `O(实体数 + 玩家数 × 可见房间数)`。`01-tick-protocol.md` 的伪代码仍写成 `build_snapshot(player_id)` 对 `all_entities` 做 `visibility_filter`，虽然后文又说“快照按房间序列化一次”。这不是单纯示例问题，因为该伪代码定义了函数接口和复杂度直觉。

影响分析：
- 实现者可能按伪代码实现 per-player all_entities filter，重新引入 `O(P × E)` 路径。
- Snapshot Contract、visibility cache、MCP query 同源快照的边界会不清楚。
- 性能合同中的 snapshot build/stitching benchmark 难以对应具体阶段。

修复建议：
- 将 §2.3 伪代码改为 `build_world_snapshot(tick) -> RoomShardSnapshot[]` 与 `stitch_player_snapshot(player_id, room_shards) -> Snapshot` 两个函数。
- 明确 `visibility_filter` 的输入是候选 room shards，而不是全量 `all_entities`。
- 将 snapshot benchmark 拆成 `world_snapshot_build`、`room_shard_serialize`、`player_snapshot_stitch` 三项。

### A6 — Medium — Manifest 中 entity creation 可见性规则与 Build/Spawn 的 inline/deferred 语义混杂

位置：
- `/tmp/swarm-review-R35/specs/core/06-phase2b-system-manifest.md:111`
- `/tmp/swarm-review-R35/specs/core/06-phase2b-system-manifest.md:117`
- `/tmp/swarm-review-R35/specs/core/06-phase2b-system-manifest.md:136`
- `/tmp/swarm-review-R35/specs/core/06-phase2b-system-manifest.md:142`
- `/tmp/swarm-review-R35/specs/core/06-phase2b-system-manifest.md:156`
- `/tmp/swarm-review-R35/specs/core/06-phase2b-system-manifest.md:161`
- `/tmp/swarm-review-R35/specs/core/06-phase2b-system-manifest.md:369`
- `/tmp/swarm-review-R35/specs/core/06-phase2b-system-manifest.md:371`

问题描述：
S03 Build 声明 `Entity creation: immediate, inline — structure appears in current tick`；S08 Spawn 声明新 drone 追加到 `pending_entities`；但 §3 又统一声明所有新实体都追加到 `pending_entities`，在当前 tick 所有 system 执行完毕后 flush。Build 和 Spawn 对“同 tick 后续命令是否可见新实体”的架构语义不同，但 manifest 同时给出全局统一规则与局部例外，缺少清晰抽象。

影响分析：
- Phase 2a command loop 中后续命令能否攻击/transfer/build around 新 structure 不明确。
- Build 的 immediate visibility 可能绕过 Spawn pending 不可见的 TOCTOU 保护模式，产生 action ordering 策略漏洞。
- EntityId 分配器与 pending flush 规则若对不同 creation path 不同，会影响 replay determinism。

修复建议：
- 定义统一的 Entity Creation Visibility Contract：每种创建路径必须标注 `visible_same_tick` 与 `interactable_same_tick`。
- 若 Build 必须 immediate，则解释为什么 Build 不产生 Spawn 类 TOCTOU，并在 command validation 中加入后续命令可见性规则。
- 更一致的架构是所有 creation 都进 pending queue，当前 tick 不作为玩家命令目标；若需要 terrain occupancy 立即生效，可单独写入 `ReservedTile` 而非完整 Structure entity。

### A7 — Medium — API Registry 声称容量为唯一权威，但 Command Validation 仍重列且出现陈旧容量叙述

位置：
- `/tmp/swarm-review-R35/specs/reference/api-registry.md:532`
- `/tmp/swarm-review-R35/specs/reference/api-registry.md:534`
- `/tmp/swarm-review-R35/specs/reference/api-registry.md:544`
- `/tmp/swarm-review-R35/specs/reference/api-registry.md:545`
- `/tmp/swarm-review-R35/specs/reference/api-registry.md:546`
- `/tmp/swarm-review-R35/specs/core/02-command-validation.md:575`
- `/tmp/swarm-review-R35/specs/core/02-command-validation.md:582`
- `/tmp/swarm-review-R35/specs/core/02-command-validation.md:584`

问题描述：
API Registry §5 明确“全局容量限制”为权威上限，所有其他文档不得重新声明。但 `02-command-validation.md` §6 仍重列 MAX_COMMANDS、MAX_DRONES 等限制，并且 `MAX_DRONES_PER_PLAYER` 行写有“默认 50。基准容量目标: 50 players × 10 drones = 500 total”，这与 Registry 的 target 500 active players / global drone cap 10000 / per-room drone cap 500 叙述不一致。

影响分析：
- 容量限制的单事实源被削弱，后续 IDL 生成更新后手写表容易变成 stale contract。
- 实现者可能按 command-validation 的旧容量目标配置测试，而不是按 registry 硬上限。

修复建议：
- `02-command-validation.md` 中只保留“字段校验需要读取 Limits Manifest/API Registry”的引用，不重列数值。
- 若为了读者方便必须展示，标注为非权威 excerpt，并由生成脚本注入，不能手写。
- 删除或更新 “50 players × 10 drones = 500 total” 这类陈旧容量解释。

### A8 — Low — 多处相对链接从当前文档位置看路径错误，降低文档可导航性

位置：
- `/tmp/swarm-review-R35/design/engine.md:210`
- `/tmp/swarm-review-R35/design/engine.md:267`
- `/tmp/swarm-review-R35/design/engine.md:442`
- `/tmp/swarm-review-R35/design/tech-choices.md:3`
- `/tmp/swarm-review-R35/design/tech-choices.md:64`

问题描述：
位于 `design/` 目录的文档多次链接 `specs/core/...`，从相对路径看应为 `../specs/core/...`。例如 `design/engine.md` 中 `[Complete Tick Execution Manifest](specs/core/06-phase2b-system-manifest.md)` 会解析到 `design/specs/core/...`。

影响分析：
- 不影响核心架构，但会阻碍读者从 design 意图跳转到 spec 合同。
- 自动文档检查可能无法覆盖跨目录引用，导致长期腐化。

修复建议：
- 修正 design 文档中的 specs 链接为 `../specs/...`。
- 在 docs CI 增加 markdown link check，至少覆盖本次审查涉及的 design/specs/reference 路径。

## 3. 亮点

- `api-registry.md` 作为 IDL 生成的 API 单事实源方向正确，CommandAction、RejectionReason、Host Functions、容量限制集中注册，能显著降低 SDK/codegen 分叉风险。
- `01-tick-protocol.md` 的 Shadow Write + Atomic Publish 模型比 per-room commit + rollback 更清晰，GlobalTickCommit 作为唯一 publish 点符合全局原子 tick 语义。
- `06-phase2b-system-manifest.md` 引入 Stable system IDs、R/W matrix、manifest hash、unique writer contract，是架构层面约束 ECS determinism 的正确抽象。
- `04-wasm-sandbox.md` 的 deferred command model 明确禁止 mutating host functions，把玩家代码与世界状态修改隔离在 Command Validation 单一路径之后，接口直观且安全边界清楚。
- `05-persistence-contract.md` 对 TickCommitRecord、RichTraceBlob、WASM blob 的分层目标是正确的：replay-critical 小对象进 FDB，rich/debug 大对象异步进 object store，方向上避免了跨存储双写耦合。
- 文档整体体现了“设计即目标状态”的原则，没有把核心机制写成临时 MVP；这对实现者建立最终架构心智模型很重要。

## 4. CrossCheck — 需要跨方向检查

- CX1: Special attack 的 8 种核心动作与 `special-attack-table.md` 的 canonical 参数是否完全一致，尤其 Leech/Fabricate 在 core/custom 边界上的身份 → 建议 Gameplay/API 方向检查 special attack 参数表、IDL schema、SDK wrapper 是否同源生成。
- CX2: `NotVisibleOrNotFound` 与 `TargetNotVisible` 同时存在，且 command validation 表中部分操作仍使用 `ObjectNotFound`，可能形成 visibility oracle → 建议 Security 方向检查所有 target 校验的错误优先级与 player/admin trace redaction。
- CX3: cgroup CPU quota、Wasmtime fuel、wall-clock timeout 的三重预算可能导致实际 live tick 失败分类不稳定 → 建议 Performance/Sandbox 方向检查 fuel schedule、CFS throttle 指标、timeout/fuel_exhausted 归因。
- CX4: Deploy 状态机中 object store upload pending/failed 与 `swarm_get_deploy_status`、activation_tick、prewarm registry 的交互可能存在边界条件 → 建议 Persistence/API 方向检查 deploy manifest、prewarm cache、rollback window 的状态机闭合性。
- CX5: Markdown 中多个链接指向未授权本轮未读文档，如 Snapshot Contract、Resource Ledger、special-attack-table；这些被引用为权威源但本轮未验证 → 建议 Speaker/Docs 方向在 Phase 2 汇总时检查所有权威引用链是否存在断链或循环权威。
