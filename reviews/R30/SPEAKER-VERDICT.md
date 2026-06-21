# R30 Speaker 裁决

## 裁决概要（基于 Phase 1）

**整体 Verdict: REQUEST_MAJOR_CHANGES**

10/10 reviewer 报告已逐份读取并纳入综合；无缺失报告。

### 投票统计（5×2 matrix）

| Verdict | 票数 | 来源 |
|---|---:|---|
| APPROVE | 0 | 无 |
| CONDITIONAL_APPROVE | 3 | rev-dsv4-architect, rev-dsv4-apidx, rev-dsv4-determinism-perf |
| REQUEST_MAJOR_CHANGES | 7 | rev-dsv4-security, rev-dsv4-design-economy, rev-gpt-architect, rev-gpt-security, rev-gpt-design-economy, rev-gpt-apidx, rev-gpt-determinism-perf |
| REJECT | 0 | 无 |

### 方向 × 模型矩阵

| Direction | DSV4 | GPT |
|---|---|---|
| Architect | CONDITIONAL_APPROVE | REQUEST_MAJOR_CHANGES |
| Security | REQUEST_MAJOR_CHANGES | REQUEST_MAJOR_CHANGES |
| Design & Economy | REQUEST_MAJOR_CHANGES | REQUEST_MAJOR_CHANGES |
| API/DX | CONDITIONAL_APPROVE | REQUEST_MAJOR_CHANGES |
| Determinism & Performance | CONDITIONAL_APPROVE | REQUEST_MAJOR_CHANGES |

### Speaker 判定

本轮设计总体方向成立，但存在 5 个满足“≥2 方向 + ≥2 模型”条件的共识 Blocker，且另有多项单方向双模型 High 与用户裁决项。当前不可进入实现；需先完成 B-items 与 D-items 的设计闭合。

---

## 共识 Blocker（B1..B5）

### B1 — ECS Status / Special Attack 执行模型不闭合，存在并行写入与唯一写者冲突

- **问题描述**: `06-phase2b-system-manifest.md` 同时声明 S16-S22 并行、S16-S21/S22 写 `StatusState`，又声明 `status_advance_system` S22 是唯一 StatusState writer。特殊攻击来源也在 S01、S14、S11-S13、PendingSpecialAttackIntent 之间不一致；Leech/Fabricate 是否完整参与 reducer 也未闭合。
- **来源 reviewer**: rev-dsv4-architect H1/H2/CX1/CX3/CX5；rev-dsv4-determinism-perf H1；rev-gpt-architect A-H3/A-M1；rev-gpt-determinism-perf DNP-1；rev-gpt-apidx APIDX-H2/H4；rev-gpt-design-economy D&E-7。
- **影响范围**: ECS 调度、Bevy 并行安全、Replay checksum、CommandAction SDK surface、特殊攻击 gameplay、TickTrace rejection/fuel 记录。
- **修复方向建议**: 将 Status Effects 拆成“并行 intent/effect buffer 产生”与“串行唯一 committer”。S16-S21 仅读取现有 status/subtype 并写 typed buffer；S22 移出 Parallel Set，作为唯一 `StatusState` writer。S01/Phase 2a 明确写入 `PendingSpecialAttackIntent`；S14 只读取该 buffer 并做 reducer，不从 S11-S13 读取玩家特殊攻击。8 个特殊攻击若属于目标设计，必须全部具备 validation matrix、reducer priority、unique writer、R/W matrix 与 API Registry 闭合。

### B2 — Room-partition / cross-room 事务语义与 tick 原子性冲突

- **问题描述**: 500/1000 player 目标容量要求 room-level partition，但文档同时保留 single world transaction、cross-room 2PC、`fallback to best-effort` 等互斥语义。`best-effort` 允许 source room/target room 半提交，破坏 tick occurred/did-not-occur 的二值原子性。
- **来源 reviewer**: rev-gpt-architect A-H2；rev-gpt-determinism-perf DNP-2；rev-dsv4-security M4/CX2；rev-dsv4-determinism-perf M2/CX3；rev-gpt-security CX4。
- **影响范围**: FDB schema、global tick head、cross-room movement/transfer/attack、resource ledger、hash chain、replay verifier、capacity admission。
- **修复方向建议**: 目标架构直接统一为 room-partition tick commit；single transaction 仅可作为 dev/test profile。删除 `best-effort` gameplay state fallback。定义 `GlobalTickCommit { tick, per_room_commit_hashes, cross_room_intent_set, global_resource_ledger_hash, manifest_hash }`。Cross-room intent 必须 canonical log + deterministic coordinator + all-or-reject；超时则 deterministic reject/abort 或 tick abandon + snapshot restore，不允许部分生效。

### B3 — CommandAction / Registry / validation / docs 派生面不一致，SDK surface 不可实现

- **问题描述**: API Registry 声明 21 个 CommandAction 及公共 `object_id`，但 commands/validation/manifest 对 Spawn、Build、Recycle、TransferToGlobal/FromGlobal、Leech/Fabricate、特殊攻击处理器的字段名、执行路径和可用性描述不一致。公共 `object_id` 与 Spawn/GlobalStorage/Overload 的 actor/target 语义混淆。
- **来源 reviewer**: rev-gpt-architect A-H3/A-M3；rev-gpt-apidx APIDX-H2；rev-dsv4-apidx H3/L1/L3；rev-dsv4-architect M1/CX5；rev-gpt-design-economy D&E-7；rev-dsv4-design-economy M2/CX5。
- **影响范围**: TypeScript/Rust SDK discriminated union、WASM output JSON、schema validation、player examples、AI agent codegen、TickTrace command/rejection hash。
- **修复方向建议**: 以 IDL/Registry 为唯一机器源，生成 canonical CommandAction JSON representation 与示例。统一 `actor_id`/`object_id`/`spawn_id`/`target_id` 语义：建议将执行主体命名为 `actor_id`，Spawn 明确 `actor_id = spawn entity id` 或移除重复 `spawn_id`；Global Storage 若非实体动作，应进入 EconomyOperation lane。21 个 action 在 validation matrix、handler manifest、R/W matrix、SDK examples 中一一闭合。

### B4 — RejectionReason / JSON-RPC Error Envelope / debug detail 合同分叉

- **问题描述**: Registry 的 canonical `rejection_reason`、`debug_detail` 与 interface.md 的 `swarm_error/details/retry_allowed`、api-registry 中的 `rejection_detail` 并存；validation 文档仍列出未注册失败码（如 `StillSpawning`, `MainActionQuotaExceeded`, `TileBlocked` 等），但未明确映射为 canonical enum 或 debug_detail。
- **来源 reviewer**: rev-dsv4-apidx H2/M2；rev-gpt-apidx APIDX-H3/APIDX-H4；rev-gpt-determinism-perf DNP-8；rev-dsv4-architect CX6；rev-gpt-security CX1/CX5。
- **影响范围**: SDK typed exception、competitive/practice/training hint ladder、安全脱敏、TickTrace rejection hash、replay verifier、MCP/Web UI 错误处理。
- **修复方向建议**: 统一单一 SwarmError envelope：保留 `rejection_reason` 作为 canonical wire enum，可补充 `retry_allowed`、`idempotency_key`、`retry_after_tick` 等 machine-readable 字段，但不得另起 `swarm_error`。删除或明确定义 `rejection_detail` 与 `debug_detail` 的差异；推荐只保留 `debug_detail`。为所有 validation failure 建立生成表：`condition -> canonical RejectionReason -> debug_detail template`，CI 检查非 canonical label 不进入 wire enum。

### B5 — TickTrace / replay-critical / rich trace 持久化术语与失败语义冲突

- **问题描述**: `01-tick-protocol.md` 声称 TickTrace 与 tick 执行同一 FDB transaction，失败则 tick 放弃；`05-persistence-contract.md` 则将 replay-critical subset 放 FDB、rich/debug blob 异步上传，并允许 `audit_gap`。裸用 `TickTrace` 同时指 FDB critical record、rich blob 与 replay artifact。
- **来源 reviewer**: rev-gpt-architect A-H1；rev-gpt-determinism-perf DNP-3；rev-dsv4-security 亮点/CX6 涉及 persistence 分层与审计日志；rev-gpt-security 亮点确认 persistence 分层；rev-dsv4-determinism-perf 亮点确认 COLLECT/replay 架构但指出相关 envelope 漂移。
- **影响范围**: FDB transaction 结构、object store async upload、audit_gap terminal state、anti-cheat audit、replay verifier、WAL/hash chain、告警等级。
- **修复方向建议**: 禁止裸用 `TickTrace` 表示不同层。统一术语为 `TickCommitRecord`（FDB replay-critical，同事务必交）、`RichTraceBlob`（object store debug/rich trace，可异步失败）、`ReplayArtifact`（由 critical subset + keyframe/delta 重建）。修改 `01-tick-protocol.md`：只有 `TickCommitRecord` 写入失败才 tick abandon；`RichTraceBlob` 失败只产生 `audit_gap`，不回滚 gameplay state。

---

## CrossCheck 汇总（Phase 2 补漏清单）

本轮无独立 Phase 2 报告；以下为 Phase 1 reviewer 明确提交的 CrossCheck 补漏方向，供后续 Phase 2 分派。

| 目标方向 | CrossCheck 项 | 来源 |
|---|---|---|
| Architect / Engine | Status Effects R/W matrix 与 Unique Writer Contract 仲裁；Bevy component access 粒度验证；S14 intent 来源修正 | rev-dsv4-architect, rev-dsv4-determinism-perf, rev-gpt-determinism-perf |
| Persistence / Determinism | Room-partition 2PC、cross-room rollback、global tick head、best-effort 删除后的确定性失败语义 | rev-gpt-architect, rev-gpt-security, rev-gpt-determinism-perf, rev-dsv4-security |
| API / Tooling | MCP 工具计数、CommandAction 数量、IDL/codegen 是否真实覆盖 mcp-tools/commands/validation 派生文档 | rev-dsv4-apidx, rev-gpt-apidx, rev-gpt-design-economy |
| Security / API | `NotVisibleOrNotFound`、`ERR_NOT_VISIBLE`、`ObjectNotFound`/`TargetNotVisible` 的 oracle 边界；debug_detail 在 practice/training 下的信息泄露 | rev-dsv4-security, rev-gpt-apidx, rev-gpt-determinism-perf |
| Economy / Gameplay | global transfer delay、Allied Transfer 默认启用状态、PvE budget 分母、RCL death spiral、Overload 长期压制 | rev-dsv4-design-economy, rev-gpt-design-economy, rev-gpt-determinism-perf |
| Security / Protocol | WebSocket per-message signature 与 SDK ergonomics；header vs frame-level MAC；seq 断线恢复 | rev-gpt-security, rev-gpt-apidx |
| Sandbox / Performance | cgroup/seccomp/net namespace OS 开销、CPU quota vs fuel/deadline、SIMD deterministic subset | rev-dsv4-security, rev-dsv4-determinism-perf, rev-gpt-security, rev-gpt-determinism-perf |
| Modding / Economy | Rhai `actions.award/deduct` 是否绕过 Resource Ledger；mod package provenance 与 trust policy | rev-gpt-apidx, rev-gpt-security |
| Product / Arena | Arena victory/scoring contract、tournament toolset 是否属于核心目标、simulate/dry-run 竞技公平 | rev-gpt-design-economy, rev-gpt-determinism-perf |

---

## 方向专属 High

以下项目未满足“≥2 方向 + ≥2 模型”共识 Blocker 门槛，但在所属方向内为 High/Critical，应作为方向修复任务处理。

### Architect

- **A-H1**: MCP/Admin mutation 与 tick command ordering lane 边界冲突。来源：rev-gpt-architect A-H4；相关 rev-gpt-security S-H3。建议拆分 `GameplayCommandLane` / `ControlMutationLane` / `ReadQueryLane`。
- **A-H2**: Snapshot 构建接口仍保留 per-player O(P×E) 直觉。来源：rev-gpt-architect A-M2、rev-gpt-determinism-perf DNP-9、rev-dsv4-determinism-perf M5。建议改为 `WorldSnapshotFrame` + `PlayerSnapshotView` 双层合同。

### Security

- **S-H1**: Host Function `ERR_NOT_VISIBLE` 形成 visibility oracle。来源：rev-dsv4-security C1/H3；相关 rev-gpt-apidx CX6。建议移除 `ERR_NOT_VISIBLE`，不可见/不存在统一过滤为空或 `NotVisibleOrNotFound`。
- **S-H2**: WebSocket 会话内签名合同冲突。来源：rev-gpt-security S-H1；相关 rev-gpt-apidx CX3。建议 Agent/CLI sensitive WS frame 强制 seq + MAC/signature。
- **S-H3**: CSR admission control 被弱化为 PoW-only。来源：rev-gpt-security S-H2；rev-dsv4-security M1 关注 challenge race。建议统一多层 L1-L6 admission。
- **S-H4**: Admin rate limit “无限制”与 admin_critical 限速/审计冲突。来源：rev-gpt-security S-H3。建议所有 admin 操作按 Registry 限速、counter、idempotency、双签/审计。
- **S-H5**: sandbox 网络隔离语义冲突。来源：rev-gpt-security S-H4；rev-dsv4-architect CX4。建议独立 net namespace + 无外部接口为强合同。
- **S-H6**: managed-by-server 私钥风险。来源：rev-dsv4-security H2。建议默认关闭、短 TTL、HSM/KMS 或隔离加密、append-only hash-chain audit。
- **S-H7**: 联邦 CRL 180s 吊销窗口过大。来源：rev-dsv4-security H1。建议缩短同步/过期窗口或实时 CRL check。

### Design & Economy

- **D-H1**: Standard 经济曲线全场景净负，缺少 break-even / equilibrium 证明。来源：rev-dsv4-design-economy C1/C3；rev-gpt-design-economy D&E-1。需 D2 裁决。
- **D-H2**: `global_transfer_delay` / `transfer_to_global_time` / `transfer_from_global_time` 三套值冲突。来源：rev-dsv4-design-economy C2；rev-gpt-design-economy D&E-2。需 D1 裁决。
- **D-H3**: Allied Transfer 当前设计边界冲突。来源：rev-gpt-design-economy D&E-3；rev-dsv4-design-economy M3/CX6。需 D3 裁决。
- **D-H4**: PvE budget “世界再生总量 ×30%” 分母未定义。来源：rev-dsv4-design-economy H3。建议 Resource Ledger 定义 `Σ source_def.regeneration`。
- **D-H5**: Controller aging `controller_count` 公式语义模糊。来源：rev-dsv4-design-economy H2。建议简化为固定 50% cap 或明确定义 per-controller。

### API/DX

- **API-H1**: MCP 工具计数与分组漂移。来源：rev-dsv4-apidx H1/M3；rev-gpt-apidx APIDX-H1。建议 IDL/codegen 生成所有计数，解释性文档不得手写。
- **API-H2**: Host Function ABI 成功返回值 `bytes_written` vs `0=success` 冲突。来源：rev-gpt-apidx APIDX-H5；rev-dsv4-apidx 亮点但未标问题。建议统一 `ret >= 0 = bytes_written`。
- **API-H3**: `swarm_simulate` schema 与设计说明不一致。来源：rev-gpt-apidx APIDX-H6。建议定义单一 product API，与 `swarm_dry_run` 分离。
- **API-H4**: `swarm_deploy` 二进制上传形态不清。来源：rev-gpt-apidx APIDX-H7；rev-dsv4-security M5。建议 `wasm_base64` / `upload_ref` tagged union + module_hash/idempotency。

### Determinism & Performance

- **P-H1**: Sandbox CPU cgroup 配额、fuel、2500ms deadline 语义冲突。来源：rev-gpt-determinism-perf DNP-4；rev-dsv4-determinism-perf M3/CX4。建议明确 fuel 为计算配额、cgroup 为 runaway guard，或改为正式 CPU-time budget。
- **P-H2**: 1000-player 容量推导算术与 worker_pool 默认值不匹配。来源：rev-gpt-determinism-perf DNP-5。建议按 `ceil(active_players / worker_pool_size) × p99_wasm_time + overhead` 重写模型。
- **P-H3**: TickInputEnvelope 字段列表过期。来源：rev-dsv4-determinism-perf H2。建议 engine.md 不重复字段，引用 api-registry §6。
- **P-H4**: Initial world_seed 持久化缺失与 S14 merge sort tiebreaker 不完整。来源：父任务 handoff rev-gpt?（t_fe4483c9）报告摘要；需在 Phase 2 重新核对全文位置。
- **P-H5**: WASM RNG host 合同不完整。来源：rev-gpt-determinism-perf DNP-7。需 D6 裁决。

---

## Medium / Low 处置

| 项 | Severity | 来源 | 处置建议 |
|---|---|---|---|
| Phase/MVP/Future/Tier 语言残留 | Medium/Low | rev-gpt-architect A-L2, rev-gpt-design-economy D&E-4/D&E-7, rev-gpt-apidx APIDX-M2, rev-dsv4-apidx H3 | 直接闭合：全局替换为目标状态、Optional Extension、Out of Scope、world_action_manifest capability；不得用阶段词表达 API 可用性 |
| Storage tax tier 重复声明 | High/Medium | rev-dsv4-design-economy H1/CX3 | 直接闭合：gameplay 删除数值表，引用 Resource Ledger |
| Balance Sheet 存储税计算不透明 | Medium | rev-dsv4-design-economy M1 | 直接闭合：补利用率假设与可复算公式 |
| Drone P2P Offer 与 Resource Ledger Future RFC 冲突 | Medium | rev-gpt-design-economy D&E-5 | 直接闭合或 D-item 后闭合：Message 仅为非原子协商层，实际资源流只走 Ledger |
| Arena victory/scoring 合同不一致 | Medium | rev-gpt-design-economy D&E-6 | 需 D4 裁决后闭合 |
| canonical_json NFC 跨语言一致性 | Medium | rev-dsv4-determinism-perf M1, rev-gpt-determinism-perf DNP-6 | 直接闭合：记录 Unicode/canonical_codec_version，CI Rust/Go hash fixture |
| seeded shuffle modulo bias / active player order | Medium | rev-gpt-determinism-perf DNP-6 | 直接闭合：PlayerId canonical sort + rejection sampling |
| Room-partition 2PC 性能 benchmark | Medium | rev-dsv4-determinism-perf M2 | 并入 B2 修复与 benchmark gate |
| Bevy schedule graph verification | Medium | rev-dsv4-determinism-perf M4 | 并入 B1 修复后增加 CI |
| Snapshot stitching 500-player benchmark | Medium | rev-dsv4-determinism-perf M5 | 直接闭合：拆分 room shard serialization / player view stitching benchmark |
| `swarm_deploy` audit 脱敏 wasm_bytes | Medium | rev-dsv4-security M5 | 直接闭合：审计只存 module_hash/metadata_hash，敏感参数 REDACTED |
| refresh token / cert TTL 分叉 | Medium | rev-gpt-security S-M2 | 直接闭合：API Registry 为机器权威，设计文档只引用 |
| token auth 与应用层证书主认证路径歧义 | Medium | rev-gpt-security S-M3 | 直接闭合：token 工具限定 browser_web_compat，Agent/CLI 必须 cert signature |
| Rhai ABI stringly-typed | Medium | rev-gpt-apidx APIDX-M1 | deferred：建立 Rhai ABI manifest/codegen，可作为 R31 API/DX 增强 |
| relative links 404 | Low | rev-gpt-apidx APIDX-L1 | 直接闭合：markdown link check + 修正 design 到 specs 的 `../` 路径 |
| Decay Parallel Set C 标签残留 | Low | rev-dsv4-architect L1, rev-dsv4-determinism-perf L1 | 直接闭合：改为 serial World Maintenance |
| onboarding funnel 时间轴碎片化 | Low | rev-gpt-design-economy D&E-8 | deferred：不阻塞架构，但应补一张 funnel 表 |
| same_origin_account_group_quota IP 脆弱 | Low | rev-dsv4-design-economy L1 | deferred：作为 anti-abuse config 默认/文档改进 |
| MIN_LIFESPAN 未入权威参数表 | Low | rev-dsv4-design-economy L2 | 直接闭合：加入 Resource Ledger 或 API Registry capacity table |
| CVE-SLA 非 Rust 依赖覆盖 | Low | rev-dsv4-security L1 | 直接闭合：加入 Go/Gateway/frontend dependency SLA |
| certificate-only request test | Low | rev-dsv4-security L2 | 直接闭合：前端/网关集成测试 |
| SIMD deterministic subset | Low/Medium | rev-dsv4-security L3/CX3 | deferred：若开启 SIMD，需跨架构 CI；默认禁用可降低优先级 |

---

## D-items

### D1: Global Transfer 延迟权威值

- **背景**: Resource Ledger 写 `global_transfer_delay = 100 tick`；gameplay/API IDL 写 `transfer_to_global_time = 10`、`transfer_from_global_time = 5`。延迟数值决定物流是战术级近实时补给，还是战略级预调度。
- **方案A**: 拆分为 `global_deposit_delay` 与 `global_withdraw_delay`，推荐默认 deposit 10 / withdraw 100。入库较快、出库慢，符合 “No Teleport” 与前线补给约束。— **推荐**
- **方案B**: 保持 10/5 tick 轻物流体验，并降低文档中 “No Teleport / 战略物流” 的强声明。— **不推荐**，因为会削弱物流战与拦截窗口的意义。
- **Speaker 推荐**: A。理由：保留轻量可用性同时防止全局仓库成为准即时传送补给；也能解释三层物流模式的策略差异。

### D2: Standard 经济是否必须展示 break-even 正流量窗口

- **背景**: Balance Sheet 四个场景全部净负，但 Growth Path 声称 Full economy 可自维持。Anti-snowball 目标应是“扩张可行但边际递减”，不是所有展示点永久赤字。
- **方案A**: 补 authoritative break-even/equilibrium table，展示至少一个小规模正流量稳定点，并计算 1/2/3/5/10/20/50 rooms 的 income/upkeep/tax/net。— **推荐**
- **方案B**: 明确 Vanilla Standard 是净赤字设计，玩家长期依赖 starting resources + PvE faucet；同步删除“自维持/轻微盈余”表述。— **不推荐**，会让 World 持久经济更像消耗赛，学习曲线风险高。
- **Speaker 推荐**: A。理由：更符合可持续 World、anti-snowball 与新手成长目标；数值表也可作为后续 benchmark/playtest gate。

### D3: Allied Transfer 在 Standard World 的目标状态

- **背景**: 文档同时说 Standard 默认禁用、MVP/当前必须实现 Restricted Cooperation、Resource Ledger 当前规则已包含 Allied Transfer。该功能影响联盟经济、feeding/smurf 风险与物流战。
- **方案A**: Standard 默认启用 Restricted Allied Transfer：有 fee/delay/cap/intercept，Novice/Tutorial 可禁用或弱化，Arena 禁用。— **推荐**
- **方案B**: Standard 默认禁用 Allied Transfer，仅 Alliance/Custom World profile 启用；核心文档将其移为 optional profile capability。— **不推荐**，会削弱联盟经济与物流战作为核心 World 深度。
- **Speaker 推荐**: A。理由：与“Restricted Intercept/Restricted Cooperation 作为目标设计”一致；用费用、延迟、cap、拦截和审计抑制雪球，而不是默认移除玩法。

### D4: Arena 胜利条件的单一目标函数

- **背景**: modes.md 写 drone=0 / surrender / timeout asset tiebreaker；feedback-loop 写摧毁 Spawn 或时限分高者胜。Arena 是算法竞技核心，目标函数必须唯一。
- **方案A**: Primary = 摧毁敌方 Spawn；Secondary = enemy active drone count 归零；Timeout = weighted score（spawn alive、active drones、structures、resources、damage dealt、map control）。— **推荐**
- **方案B**: Primary = enemy active drone count 归零；Spawn destroyed 仅作为高权重 score/tiebreaker。— **不推荐**，可能鼓励纯猎杀 drone 而非基地战略，也弱化 Spawn 的竞技叙事。
- **Speaker 推荐**: A。理由：Spawn 是更清晰的竞技目标与观战叙事；drone=0 可作为快速胜利条件或次级判定。

### D5: Leech / Fabricate 是否作为 8 个特殊攻击的核心目标设计

- **背景**: gameplay 写 Standard 全部 8 种特殊攻击可用；API Registry 将 Leech/Fabricate 标为 Tier 2；validation/manifest 只完整覆盖 6 个。阶段化标签违背“设计即目标状态”。
- **方案A**: 8 个特殊攻击全部作为核心目标设计，删除 Tier 2/未来语义，补齐 Leech/Fabricate 的 validation matrix、reducer priority、R/W matrix、status/effect、SDK examples。— **推荐**
- **方案B**: 核心只保留 6 个，Leech/Fabricate 移出 core CommandAction，作为 optional world_action_manifest/mod capability。— **不推荐**，会与当前 gameplay 学习曲线和专家层深度表冲突。
- **Speaker 推荐**: A。理由：更符合本轮 clean target-state 原则；避免 SDK 暴露 gated stub 和玩家可用性歧义。

### D6: 玩家 WASM deterministic RNG 合同

- **背景**: tick-protocol 提到 `swarm_get_random(sequence)`，但 Sandbox/API Registry 未注册该 host function；同时又说不暴露 RNG/entropy。玩家策略随机性需要明确来源。
- **方案A**: 不提供 RNG host function；玩家只能使用 snapshot 中公开 deterministic seed/material 自行实现 PRNG，SDK 提供纯库 helper。— **推荐**
- **方案B**: 新增 `host_get_random(sequence, out_ptr, out_len)`，注册 ABI/fuel/call limit/domain separation/sequence monotonic/replay hash，返回 per-player deterministic stream。— **不推荐**，增加 host ABI 与安全审计面，且容易被误解为 engine entropy。
- **Speaker 推荐**: A。理由：保持 host function surface 最小，避免 world_seed 泄露/预测争议；SDK helper 足以满足玩家策略随机性。

### D7: WebSocket Agent 每消息认证强度

- **背景**: auth.md 写握手后消息免签；MCP security/API Registry 写每条 Agent WS 消息 seq + MAC/signature。强合同影响 SDK ergonomics，但弱合同扩大会话注入/重放风险。
- **方案A**: Agent/CLI 可写或敏感 WS frame 必须 per-message seq + MAC/signature；Browser read-only spectator WS 可免每消息签名但不可承载 mutation。— **推荐**
- **方案B**: 仅握手签名，连接内消息依赖 session binding；用 TLS/反向代理保证通道完整性。— **不推荐**，不符合应用层证书和审计不可抵赖目标。
- **Speaker 推荐**: A。理由：安全收益显著，SDK 可封装 seq/signature，用户不必手写。

---

## 最终裁决

**REQUEST_MAJOR_CHANGES** — 本轮不得进入实现。先闭合 B1-B5 与 D1-D7；方向专属 High 中可直接修复项应并行收敛，Medium/Low 按表执行 direct close 或 deferred。

---

## D-items 裁决记录（2026-06-21）

| ID | 裁决 | 详情 |
|----|------|------|
| D1 | **A — 拆分双延迟** | `global_deposit_delay`(10) + `global_withdraw_delay`(100)，均为 world.toml 可配置项 |
| D2 | **A — 补 break-even** | 添加 authoritative break-even/equilibrium table，展示至少一个小规模正流量稳定点 |
| D3 | **A — Standard 默认启用** | Standard World 默认启用 Restricted Allied Transfer（fee/delay/cap/intercept），Novice/Tutorial 可禁用，Arena 禁用 |
| D4 | **房间规则可配置** | Arena 胜利条件为 room config 可配置项：固定 tick 数 / 摧毁所有建筑 / 全灭 drones+buildings / 占领目标点连续或累计 tick 等 |
| D5 | **A — 8 个全核心 + 清理 Tier 2** | 8 个 special attack 全部作为核心目标设计，全局清理所有 Tier 2/Phase/Future 阶段化表述 |
| D6 | **B — 新增 host_get_random** | 注册 `host_get_random(sequence, out_ptr, out_len)` host function，含 ABI/fuel/call limit/domain separation/sequence monotonic/replay hash |
| D7 | **A — per-message seq + MAC** | Agent/CLI 可写或敏感 WS frame 强制 per-message seq + MAC/signature；Browser read-only spectator WS 可免签名 |