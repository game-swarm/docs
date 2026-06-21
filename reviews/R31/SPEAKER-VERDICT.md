# R31 Speaker 裁决

## 裁决概要

**整体 Verdict: REQUEST_MAJOR_CHANGES**

R31 Clean-Slate 文档已经在多个核心方向上形成了正确的目标架构：WASM deferred command model、API Registry/IDL 单事实源、确定性 ECS manifest、应用层证书、Resource Ledger、可见性防 oracle 与 replay-critical 持久化分层都被多位 reviewer 认可。但 10 份报告共同显示：当前文档集仍存在多处跨文档权威合同冲突，且这些冲突落在 tick 原子性、API/SDK wire contract、Auth audience/replay、安全沙箱、经济稳态与特殊攻击目标状态等核心边界上。

因此本轮不能通过。需要先闭合共识 Blocker 与 D-items，再进入下一轮评审。

### 评审统计（5×2 matrix）

| 方向 | DSV4 Verdict | GPT Verdict | 主要结论 |
|---|---:|---:|---|
| Architecture | CONDITIONAL_APPROVE | REQUEST_MAJOR_CHANGES | 架构方向正确，但 room-partition、API Registry、execution lane、manifest 计数冲突需修复 |
| Security | REQUEST_MAJOR_CHANGES | REQUEST_MAJOR_CHANGES | audience/transport、nonce/replay、CSR admission、sandbox/cache 等安全合同未闭合 |
| Design & Economy | REQUEST_MAJOR_CHANGES | REQUEST_MAJOR_CHANGES | Standard 经济曲线、global transfer delay、Allied Transfer、特殊攻击目标状态冲突 |
| API/DX | REQUEST_MAJOR_CHANGES | REQUEST_MAJOR_CHANGES | MCP tool count、RejectionReason、CommandAction schema、Host ABI、simulate/dry_run 漂移 |
| Determinism & Performance | CONDITIONAL_APPROVE | REQUEST_MAJOR_CHANGES | determinism 基础较强，但 room-partition、replay-critical 边界、combat R/W、WASM 输出语义需闭合 |

### 票数统计

- APPROVE: 0
- CONDITIONAL_APPROVE: 2
- REQUEST_MAJOR_CHANGES: 8
- REJECT: 0

### Provenance

已逐份读取 task body 指定的全部 10 份 Phase 1 报告：

- `/data/swarm/docs/reviews/R31/rev-dsv4-architect.md`
- `/data/swarm/docs/reviews/R31/rev-dsv4-security.md`
- `/data/swarm/docs/reviews/R31/rev-dsv4-design-economy.md`
- `/data/swarm/docs/reviews/R31/rev-dsv4-apidx.md`
- `/data/swarm/docs/reviews/R31/rev-dsv4-determinism-perf.md`
- `/data/swarm/docs/reviews/R31/rev-gpt-architect.md`
- `/data/swarm/docs/reviews/R31/rev-gpt-security.md`
- `/data/swarm/docs/reviews/R31/rev-gpt-design-economy.md`
- `/data/swarm/docs/reviews/R31/rev-gpt-apidx.md`
- `/data/swarm/docs/reviews/R31/rev-gpt-determinism-perf.md`

R31 目录当前仅有上述 10 份报告；未发现 Phase 2 补充报告。

## 共识 Blocker（B1..B8）

### B1 — Room-partition tick commit 原子性语义冲突

- **问题描述**: `01-tick-protocol.md` 与 `05-persistence-contract.md` 同时保留了全局原子 tick、All-or-Reject、2PC、单房间 rollback、其他房间独立推进、best-effort partial commit 等互相排斥语义。当前文档无法唯一回答：一个 room commit 失败时，全世界 tick 是否 abandon，还是部分房间继续推进。
- **来源 reviewer**:
  - rev-gpt-architect: A-H1
  - rev-gpt-determinism-perf: DNP-1
  - rev-dsv4-determinism-perf: M3 CrossRoomIntent timeout 与 EXECUTE budget 矛盾
  - rev-dsv4-architect: M2/S29 cross-room ledger 位置问题
- **共识判定**: Architecture + Determinism/Performance 两个方向，GPT + DSV4 两个模型均触及同一核心：room-partition / cross-room / commit / ledger 边界不闭合。
- **影响范围**: replay determinism、GlobalTickCommit、FDB transaction layout、CrossRoomIntent、resource ledger、snapshot restore、client-visible state、TickCommitRecord hash chain。
- **修复方向建议**: 必须收敛为单一目标状态机。Speaker 推荐默认目标为“全局 tick 原子”：每 tick 在内存中完成全局 deterministic simulation；room-partition 仅作为 FDB 写入分区优化；任一 per-room commit、cross-room coordinator 或 GlobalTickCommit 失败均导致该 tick abandon + 全局 snapshot restore + retry；删除“其他房间独立推进”“best-effort”语义。若用户选择局部推进，则必须重新设计 per-room tick/version、跨房间 barrier、global ledger 分片与 replay verifier partial-tick 模型。

### B2 — API Registry / IDL 单事实源破裂：工具数、错误码、CommandAction schema、Host ABI 多处漂移

- **问题描述**: Registry 声称是 API 单事实源，但派生文档和 core spec 中出现了多处机器合同漂移：MCP 工具数量 56/57/58/59 不一致；RejectionReason canonical 47 与 ad-hoc 错误码冲突；CommandAction 示例字段名与 Registry schema 不一致；Host Function 数量 5/6 不一致且 `host_get_random` 在若干文档中缺失；`swarm_simulate`/`swarm_dry_run` schema 互相冲突。
- **来源 reviewer**:
  - rev-dsv4-apidx: C1, C2, H1, H3, M1, M3
  - rev-gpt-apidx: R31-API-H1, H2, H3, H4, M1, M2, M3
  - rev-gpt-architect: A-H2, A-M1
  - rev-gpt-security: S-H4
  - rev-gpt-determinism-perf: DNP-5
- **共识判定**: API/DX + Architecture + Security + Determinism 多方向，GPT + DSV4 双模型共识。
- **影响范围**: TypeScript SDK、MCP tool discovery、JSON schema validation、typed exception、WASM import whitelist、IDE autocomplete、examples-as-tests、replay verifier。
- **修复方向建议**: 以 IDL/API Registry 为机器权威，其他文档不得手写可冲突表格或固定计数。将工具 status/count bucket、CommandAction fields、RejectionReason mappings、Host Function ABI、simulate/dry_run schema 全部生成化；CI 增加 docs-derived-counts、examples-schema-validate、error-code-lint、host-abi-consistency gate。

### B3 — Auth audience / transport / nonce / CSR admission 安全合同不闭合

- **问题描述**: Auth 文档和 MCP/security 文档中 audience 字符串存在多套格式，`agent-mcp`/`cli-rest` transport 枚举不一致；canonical request 的 audience 与证书 audience 是否逐字节匹配不明确；nonce/replay 语义同时声明强 nonce 与 Dragonfly 丢失后可重放；CSR admission control 同时要求多层限流又写“PoW 自身限速、无额外 IP 限制”；Auth API Registry 与 auth.md 的工具、TTL、权限模型不一致。
- **来源 reviewer**:
  - rev-dsv4-security: C2, H2, H3
  - rev-gpt-security: S-H1, S-H2, S-H3, S-H4
  - rev-gpt-apidx: CX-1/CX-3 涉及 auth/API collision 与 WS signature
  - rev-gpt-architect: CrossCheck audience/API Registry single source
- **共识判定**: Security + API/DX + Architecture 多方向，GPT + DSV4 双模型共识。
- **影响范围**: Gateway authn/authz、MCP Agent 连接、browser/WS/REST transport isolation、application-layer certificate、request replay defense、CSR CA signing path、SDK generated auth client。
- **修复方向建议**: 建立唯一 “Canonical Audience Format”: `swarm-aud-v1:<transport>:<server_id>:<world_id>:<subject_id>`，transport enum 进入 auth IDL/API Registry；签名 payload audience 与证书 audience 必须逐字节匹配，并额外校验实际 transport/server/world。为每个 auth/API tool 生成 replay_class → nonce strategy → rate_limit_key → required_scope 矩阵。CSR submit 必须为 PoW + per-IP + per-ASN + global semaphore + bounded queue + audit throttle。

### B4 — Standard 经济模型与自维持/anti-snowball 目标冲突

- **问题描述**: Economy Balance Sheet 中 Standard 1/2/3/5/10/20/50 房间全部净负，却同时声明 free_upkeep 后 full economy 自维持、Controller 升级后可 break-even、empire upkeep 是 anti-snowball 而非 anti-growth。DSV4 还指出 1 房间缺 drone spawn 摊销、全表缺稳态摊销模型，导致经济证明不可信。
- **来源 reviewer**:
  - rev-dsv4-design-economy: C1, C3, H1, H3
  - rev-gpt-design-economy: DE-1
  - rev-gpt-architect / rev-gpt-determinism-perf CrossCheck 提及经济/API/ledger 需要统一
- **共识判定**: Design/Economy 方向双模型强共识，并被 Architecture/Determinism 通过 CrossCheck 指向资源账本与目标状态一致性。
- **影响范围**: new player learning loop、Standard mode reward curve、anti-snowball proof、AI agent optimization target、economy dashboard、Resource Ledger 参数验收。
- **修复方向建议**: 重算 Standard 收支曲线，明确至少三个可达稳态：1-2 房 free_upkeep 后可接近平衡或略正；5-10 房通过代码效率/RCL/Source/PvE 达到正收益但边际递减；20+ 房利润明显压缩，50 房接近 soft cap。所有表必须包含 drone spawn amortization、upkeep、storage tax、controller income、source income、PvE cap share 与假设来源。

### B5 — Global / Allied Transfer 资源流目标状态冲突

- **问题描述**: Global Storage 提取延迟存在 5/10/100 tick 多套值；外交层将 allied transfer 描述为“直接免 convert 延迟”，而 Resource Ledger / Snapshot Contract 定义了 Restricted Allied Transfer（fee、delay、cooldown、daily cap、alliance age、intercept window）；TransferToGlobal/TransferFromGlobal 已在 Registry 注册但缺少 validation/manifest execution lane。
- **来源 reviewer**:
  - rev-dsv4-design-economy: C2, H2, CX-3, CX-8
  - rev-gpt-design-economy: DE-2, DE-3
  - rev-gpt-architect: A-H3
  - rev-dsv4-architect: M2/S29 cross-room resource ledger coverage
- **共识判定**: Design/Economy + Architecture 双方向，GPT + DSV4 双模型共识。
- **影响范围**: Resource Ledger、No Teleport 约束、alliance economy、daily cap、intercept gameplay、global/local storage strategy、CommandAction execution, TickTrace resource attribution。
- **修复方向建议**: 以 Resource Ledger 为经济权威，拆分并命名 `global_deposit_delay` 与 `global_withdraw_delay`（若采用现有倾向则 deposit=10, withdraw=100），同步 gameplay/API/snapshot/economy docs。外交层改为“可发起 Restricted Allied Transfer”，不得写免延迟 global player transfer。为 TransferToGlobal/TransferFromGlobal 增加 Phase 2a execution lane、validation matrix、resource ledger writes、refund semantics 与 manifest R/W entry。

### B6 — Leech / Fabricate 目标状态、校验矩阵与 body part 合同不闭合

- **问题描述**: API Registry 将 Leech/Fabricate 标为 Tier 2，但 manifest/gameplay 声明 8 种 special attack 全部是核心目标状态；DSV4 Architect 指出两者缺完整逐指令校验矩阵；API/DX 指出 body part requirement 模糊；Architecture/Determinism 指出 Registry 与 manifest action availability 冲突。
- **来源 reviewer**:
  - rev-dsv4-architect: C1, M5
  - rev-dsv4-apidx: M4
  - rev-gpt-architect: A-H2
  - rev-gpt-design-economy: DE-4
  - rev-gpt-determinism-perf: DNP-6
- **共识判定**: Architecture + API/DX + Design/Economy + Determinism 多方向，GPT + DSV4 双模型共识。
- **影响范围**: CommandAction availability、world_action_manifest、SDK generation、validator、S22a/S22b buffers、tutorial/Novice gating、replay verifier。
- **修复方向建议**: 若 R31 目标状态是 8 种 special attack 全量核心能力，则 IDL/API Registry 删除 Tier 2 标记，并补齐 Leech/Fabricate validation matrix、body part requirement、同 tick 多次命中语义、mode capability gating（如存在则进入 replay-critical manifest hash）。若不是全量核心，则 gameplay/manifest 必须撤回“全部 8 种核心能力”表述。此处含 D-item。

### B7 — Replay-critical 持久化边界与 RichTraceBlob/audit_gap 语义冲突

- **问题描述**: Persistence contract 声称 replay-critical subset 必须在 FDB 同事务提交，但持久化 Phase B 没有明确写入 commands/rejections/fuel/deploy decisions 等 §2.1 字段；对象存储 RichTraceBlob 失败有时被描述为 replay 不可用/replay gap，而 API Registry 又称 blob 缺失不影响 deterministic replay，仅降级 rich audit。
- **来源 reviewer**:
  - rev-gpt-determinism-perf: DNP-2
  - rev-dsv4-architect: 持久化分层亮点与 M2/S29 cross-room ledger 覆盖
  - rev-gpt-architect: CrossCheck TickTrace retention/Object Store TTL/audit_gap
  - rev-dsv4-security: 亮点中确认 FDB replay-critical + Object Store async 分层，但安全 C1/CVE 等指向 sandbox/persistence consistency
- **共识判定**: Determinism/Performance + Architecture 多方向，主要由 GPT 明确标 High，DSV4 报告提供同一边界的补充与验证要求。作为核心 replay/审计边界，提升为共识 Blocker。
- **影响范围**: deterministic replay、anti-cheat audit、Object Store failure recovery、terminal_state 分类、TickCommitRecord hash chain、keyframe GC、audit_gap/unreplayable 语义。
- **修复方向建议**: 明确两条路径：FDB same-tx 写 replay-critical TickCommitRecord（commands/rejections/fuel/deploy_activation_decision/canonical_codec_version 等十项字段），Object Store 仅存 RichTraceBlob/debug delta。Object Store 失败只产生 `audit_gap` / rich audit unavailable，不得破坏 deterministic replay；若 FDB replay-critical 字段缺失则 tick 必须 abandon，不允许 committed unreplayable tick。

### B8 — ECS / WASM determinism 合同局部破口：combat R/W、output limit、EntityId、S22 order

- **问题描述**: Combat Parallel Set 声称 S11-S13 并行写 HitPoints，又说 reduce 后由 S15 统一应用；WASM 输出超 256KB 同时被定义为截断前 256KB 与整批丢弃；EntityId allocator determinism 未显式合同化；S22 Phase 2 entity iteration order 未显式排序。
- **来源 reviewer**:
  - rev-gpt-determinism-perf: DNP-3, DNP-4
  - rev-dsv4-determinism-perf: H1, H2
  - rev-dsv4-architect: H2 ResourceDeltaEvent / M4 DeathMark multi-writer / manifest count
  - rev-gpt-architect: A-M2 manifest count/system authority
- **共识判定**: Determinism/Performance + Architecture 双方向，GPT + DSV4 双模型共识。
- **影响范围**: ECS parallel scheduler, Bevy R/W matrix CI, replay determinism, command parsing, tick validation, state_checksum, WASM SDK behavior。
- **修复方向建议**: S11-S13 只写 PendingDamage/PendingHeal/CombatIntent buffers，S15 唯一写 HitPoints 并按 canonical key reduce；WASM 输出超 256KB 统一为整批丢弃、不解析前缀；EntityId allocator 写入 deterministic contract 与 CI replay check；S22 Phase 2 显式 `sorted(entities_with_active_status, StableEntityId)` 并声明 per-entity buffer effect order。

## CrossCheck 补漏发现

无 Phase 2。R31 目录未发现 Phase 2 / CrossCheck 补充报告文件。

Phase 1 报告中的 CrossCheck 可归纳为以下目标方向：

| 目标方向 | CrossCheck 来源 | 需补漏检查 |
|---|---|---|
| Engine / Architecture | Security C1/C2, DNP room-partition, Economy global delay | 编译缓存键、room-partition commit、CrossRoomIntent deadline、global transfer lane 是否统一 |
| Security / Visibility | Economy Overload visibility, API host_get_random, Allied intercept oracle | PlayerId 级 visibility、RNG domain separation、intercept 可见性与通知是否泄露不可见信息 |
| API / IDL | Security Auth API, Design Leech/Fabricate, API/DX errors/tools | auth_api 是否覆盖完整 lifecycle、special attack metadata 是否生成、错误码是否 canonical |
| Gameplay / Economy | Architect Recycle carry resources, API Leech/Fabricate body part, DNP output drop UX | Recycle 资源守恒、body part/counterplay、WASM 超限整批丢弃对玩家体验是否可接受 |
| Persistence / Replay | Architect resource ledger S29, DNP TickCommitRecord, Security deploy state | Cross-room resource ledger、audit_gap、deploy activation 与 blob upload 状态机是否唯一权威 |
| Documentation / Speaker | 多份报告 | 清理 MVP/Tier/Future/Phase/Rxx 修复叙事，目标状态文档改用 Core/Optional/RFC/Benchmark-gated 等分类 |

## 方向专属 High

以下为未提升为共识 Blocker、但仍需方向闭合的 High severity 项。

### Architecture 专属 High

- **A-H1 / Build inline creation vs pending_entities**: DSV4 Architect 指出 manifest §3 “所有新实体 pending_entities 延迟可见”与 S03 Build “immediate inline”冲突。需明确 Phase 2a inline creation 与 Phase 2b deferred creation 的可见性窗口。
- **A-H2 / ResourceAmount 多写入者与 resource_ledger delta tracking 未定义**: DSV4 Architect 指出 S29 读取所有 ResourceAmount changes 但未定义 event log 或 diff 机制。建议定义 `ResourceDeltaEvent`，所有 ResourceAmount writer 显式 emit。

### Security 专属 High

- **S-H1 / Sandbox Store Reset checklist 缺失**: DSV4 Security 指出 Store reset 未明确 globals/tables/elements/host closures/WasiCtx/epoch deadline 等完整清理项。需补 complete reset checklist 与验证方法。
- **S-H2 / sandbox relaxed guard 依赖 world.mode**: DSV4 Security Medium 但安全影响较高。release 构建应无条件拒绝 relaxed，不应仅依赖可配置 world.mode。
- **S-H3 / WS signature handshake/message 参数不一致**: GPT Security 将其列 Medium，但与 API/DX CrossCheck 叠加后建议作为 Security High 跟踪：统一 timestamp 单位、nonce 长度、WS handshake/message signature payload，明确 Ed25519 是 signature 非 MAC。

### Design & Economy 专属 High

- **DE-H1 / Allied daily cap 10,000 可能功能性不可用**: DSV4 Economy 指出 cap 仅为 global storage capacity 1%，日均吞吐约 0.35 units/tick，可能使联盟经济互助失去意义。此项需要 D-item 裁决。
- **DE-H2 / Anti-Snowball proof 无数学推导**: DSV4 Economy 指出 §4 只是断言列表，缺边际 upkeep 与边际 income 的不等式证明。需补可复算推导或承认为设计假设。

### API/DX 专属 High

- **API-H1 / Refund 表重复冲突**: DSV4 API/DX 指出 `InsufficientResource` 在 refund 表中重复出现且对应不同退款策略。需区分竞争型资源不足与预计算不足，或注册更精确 canonical code。
- **API-H2 / TypeScript SDK 生成合同不足**: GPT API/DX 将其列 Medium，但对 API/DX 可实施性重要。需定义 `@swarm/sdk` 包入口、CommandAction discriminated union、error literal union、MCP client method signatures、exhaustive switch 模式。
- **API-H3 / Rhai action transaction semantics 冲突**: GPT API/DX 指出“任一失败全丢弃”与“单 action 失败跳过该 action”冲突。需定义 recoverable action error vs script panic/timeout/security violation 两层语义。

### Determinism & Performance 专属 High

- **D-H1 / Tick latency slack 为零**: DSV4 D&P 指出 3000ms interval 与 stage p95/p99 budget 总和无调度余量甚至达 3200ms。需增加 explicit slack 或收紧 budgets。
- **D-H2 / canonical_json integer format ambiguity**: DSV4 D&P 指出 `1000` / `1000.0` / `1e3` / `00100` 等 JSON number 表示未规范。需规定整数格式：无小数点、无科学计数法、无前导零。
- **D-H3 / Hack TOCTOU pre-Hack owner cache 未明示**: DSV4 D&P 指出 Hack 在 Phase 2a 仅写 PendingSpecialAttackIntent、不修改 owner 的合同需显式写入。

## Medium / Low 处置

| 项 | 来源 | Severity | 处置建议 |
|---|---|---:|---|
| Recycle carry resource 与 spawn capacity overflow | rev-dsv4-architect M1/M3 | Medium | 直接闭合：定义 carry 返还/掉落与 spawn capacity overflow 规则 |
| DeathMark 多写入者顺序 | rev-dsv4-architect M4 | Medium | 直接闭合：manifest 注释 + CI writer-order check |
| host_get_random RNG namespace 文档区分 | rev-dsv4-architect L2 | Low | 直接闭合：区分 engine ECS RNG 与 WASM per-drone RNG |
| Recovery PoW 默认关闭 | rev-dsv4-security M1 | Medium | D-item 或 deferred：安全/UX 权衡，建议与 Auth 默认策略一并裁决 |
| read_replay_safe nonce 可选 | rev-dsv4-security M2 | Medium | 直接闭合：competitive fog_of_war=true 强制 nonce；tutorial/sandbox 可选 |
| WS per-message MAC 缺 tick binding | rev-dsv4-security M3 | Medium | 直接闭合：纳入 WS signature payload 统一修复 |
| CVE monitoring 未列 std/bevy | rev-dsv4-security L1 | Low | 直接闭合：加入 Critical Rust crates 监控列表 |
| World CRL cache 60s | rev-dsv4-security L2 | Low | deferred：增加 security event push fast path |
| Refresh token grace 10s/60s | rev-dsv4-security L3 | Low | 直接闭合：统一 10s 或补设计理由 |
| Overload PlayerId visibility | rev-dsv4-economy M1 | Medium | 直接闭合：定义 `is_visible_to_player(attacker, target_player)` |
| `special_param: float` | rev-dsv4-economy M2 | Medium | 直接闭合：改 BasisPoints/fixed-point |
| Storage utilization assumptions | rev-dsv4-economy M3 | Medium | 直接闭合：补函数或标 worst-case assumption |
| Controller repair formula 可读性 | rev-dsv4-economy M4 | Medium | D-item 或直接闭合：若多 Controller 无收益是目标，明示；否则改公式 |
| PvE cap 正反馈 | rev-dsv4-economy M5 | Medium | deferred：需 balance simulation 验证 |
| Storage tax tiers 多处重复 | rev-dsv4-economy L1 | Low | 直接闭合：非权威文档引用 Resource Ledger |
| Tutorial/Novice balance sheet 缺失 | rev-dsv4-economy L2 | Low | 直接闭合：补 1/5/10 房对比表 |
| Drone age_modifier 极端 build | rev-dsv4-economy L3 | Low | 直接闭合：补设计注记 |
| command_index scope undefined | rev-dsv4-apidx M2 | Medium | 直接闭合：限定为 WASM tick CommandIntent[] 或注册 batch API |
| host-functions.md 缺 host_get_random | rev-dsv4-apidx M3 | Medium | 由 B2 闭合 |
| interface conceptual table stale | rev-dsv4-apidx M5 | Medium | 直接闭合：改为生成摘要或概念性引用 |
| `(debug_detail)` 作为错误码列 | rev-dsv4-apidx L1 | Low | 由 B2 闭合 |
| TickValidationFailed 非 canonical | rev-dsv4-apidx L2 | Low | 直接闭合：映射 SchemaViolation 或注册 Runtime code |
| Overload proof 常量未命名 | rev-dsv4-apidx L3 | Low | 直接闭合：命名 `MAX_FUEL` / `MIN_FUEL` |
| PER_CORE_MIPS 可配置性 | rev-dsv4-determinism L1 | Low | 直接闭合：world.toml 或 startup micro-benchmark |
| Seed rotation forward secrecy | rev-dsv4-determinism L2 | Low | 已闭合：文档承认确定性系统无真正前向保密 |
| Dragonfly ≤2 tick lag wording | rev-dsv4-determinism L3 | Low | 直接闭合：标注为退化追赶场景 |
| 1000-player capacity arithmetic | rev-gpt-determinism DNP-7 | Low | 直接闭合：修正 CPU-core bound 推导 |
| Snapshot per-player pseudocode | rev-gpt-determinism DNP-8 | Low | 直接闭合：拆成 world snapshot once + player stitch |
| `global_storage_public` 计划中 | rev-gpt-economy DE-7 | Low | 直接闭合：改成目标默认与可见粒度 |
| MVP/Future/Phase/Rxx 叙事 | 多报告 | Low/Medium | 直接闭合：正文目标状态化，历史移 changelog |

## D-items

### D1: Room-partition commit 采用全局 tick 原子还是局部推进模型

- **背景**: B1 显示当前文档同时保留全局原子、局部推进和 best-effort。两种模型都可能成立，但不能并存。
- **方案A: 全局 tick 原子 commit** — **推荐**
  - 每 tick 在内存中完整 deterministic simulation；room-partition 仅为 FDB 写入优化；任一 per-room commit/cross-room/GlobalTickCommit 失败导致整个 tick abandon + snapshot restore + retry。
  - 优点：与全局 replay hash、单 tick_counter、All-or-Reject、Resource Ledger、玩家可见状态最一致；修复面较小，删除冲突 wording 即可。
  - 缺点：局部故障隔离较弱，极端 FDB conflict 可能导致全世界 tick retry。
- **方案B: 局部推进 / per-room tick 模型** — **不推荐本轮采用**
  - 每个房间拥有独立 tick/version，失败房间 rollback，其他房间可推进；cross-room intent 延迟或 barrier 结算。
  - 优点：局部故障隔离强。
  - 缺点：需要重写 replay verifier、client state version、cross-room ledger、GlobalTickCommit、resource transfer semantics，超出 R31 当前设计。
- **Speaker 推荐**: A。理由：当前 Swarm 文档的 determinism/replay/ledger 均以全局 tick 为核心，A 是最小且最一致的目标状态。

### D2: Leech / Fabricate 是否为 R31 核心目标能力

- **背景**: B6 显示 API Registry 标 Tier 2，但 gameplay/manifest 声明 8 种 special attack 全部核心。用户历史偏好也明确“设计文档=目标状态，不做 Phase/MVP”，但此轮仍需显式裁决。
- **方案A: 8 种 special attack 全部 core-enabled** — **推荐**
  - 删除 Tier 2 标记，Leech/Fabricate 与其他 special attack 同级；补 validation matrix、body part、multi-hit semantics、mode gating。
  - 优点：符合 clean-slate 目标状态与 R27/R31 设计哲学；避免 SDK/manifest/replay 分叉。
  - 缺点：需要一次性补齐 Leech/Fabricate 的 gameplay counterplay 与 validation 细节。
- **方案B: Leech / Fabricate 保留为 Optional/RFC 能力** — **不推荐**
  - Registry 保留非核心状态，manifest/gameplay 撤回“全部 8 种核心能力”，S22a/S22b 从 core manifest 移出或作为 optional rule module。
  - 优点：降低当前核心复杂度。
  - 缺点：与现有目标状态文字、manifest R/W、用户偏好冲突，且会引入 feature gating/replay manifest 复杂度。
- **Speaker 推荐**: A。理由：R31 是 clean-slate 目标设计，不应保留 Tier 2/未来语义；复杂度应通过补完整合同而不是降级为阶段占位解决。

### D3: Global transfer delay 采用 deposit=10 / withdraw=100 还是统一单值

- **背景**: B5 显示 gameplay 中存在 `transfer_from_global_time=5`，Resource Ledger/Snapshot/Economy 倾向 withdraw=100，deposit=10。需要明确权威参数模型。
- **方案A: 拆分 `global_deposit_delay=10` 与 `global_withdraw_delay=100`** — **推荐**
  - deposit 较短，withdraw 较长，支持战略调度和 No Teleport 约束。
  - 优点：与 Resource Ledger/Snapshot/Economy 多数文本一致；玩法上保留物流规划深度。
  - 缺点：参数更多，需要 UI/SDK 明确命名。
- **方案B: 统一单一 `global_transfer_delay`** — **不推荐**
  - deposit/withdraw 使用同一延迟，如 100 或其他值。
  - 优点：规则简单。
  - 缺点：失去 deposit/withdraw 非对称策略空间；若取低值会削弱 No Teleport，若取高值会使存入体验迟钝。
- **Speaker 推荐**: A。理由：当前多数权威经济文档已隐含 deposit/withdraw 拆分，且更符合“全局仓库不是前线瞬移补给”的目标。

### D4: Allied Transfer daily cap 固定 10,000、提升固定 cap，还是按 GCL/规模缩放

- **背景**: DSV4 Economy 指出 10,000/day 仅为 global storage capacity 1%，日均吞吐约 0.35 units/tick，可能使联盟经济互助功能性不可用。
- **方案A: 提升为固定 100,000/day 左右** — **可选推荐**
  - 将 daily cap 提升到约 10% global capacity，使中型玩家能进行有意义援助。
  - 优点：简单、易解释、立即让联盟资源互助有意义。
  - 缺点：对不同 GCL/世界规模适配较粗，可能对小世界偏强。
- **方案B: 按接收方 GCL / world mode 缩放** — **Speaker 推荐**
  - 例如 `allied_daily_cap = max(10,000, receiver_gcl × 20,000)`，并受 world mode multiplier 限制。
  - 优点：保留新手保护，允许高 GCL 联盟协作规模随成长扩大；更符合 anti-snowball 可调模型。
  - 缺点：需要在 Resource Ledger 和 UI 中解释公式，并纳入 balance sheet。
- **Speaker 推荐**: B。理由：联盟 transfer 是经济与反雪球交界点，规模化公式比固定 cap 更稳健；但具体系数需 balance simulation 验证。

### D5: Standard economy 修复采用“早中期可正收益，大帝国递减”还是“持续净负求生”

- **背景**: B4 显示当前报表全阶段净负，但设计文字声称 self-sustaining 与 anti-snowball。需要裁决经济哲学。
- **方案A: 早中期可达正收益，大帝国边际递减/接近 soft cap** — **推荐**
  - 1-2 房可接近平衡或略正；5-10 房优秀代码可明显正收益；20+ 房利润压缩；50 房接近 soft cap。
  - 优点：保留新手学习正反馈、中阶优化空间与专家反雪球；符合“anti-snowball 而非 anti-growth”。
  - 缺点：需要重算表格与参数，可能需要多轮 balance simulation。
- **方案B: Standard 设计为持续净负，玩家必须扩张/外部输入求生** — **不推荐**
  - 承认当前全负曲线是设计目标，并删除 self-sustaining/break-even 说法。
  - 优点：规则严酷，扩张压力强。
  - 缺点：对新手与 AI agent 学习极不友好，容易把策略空间变成漏洞寻找或输血依赖。
- **Speaker 推荐**: A。理由：Swarm 的编程游戏核心应奖励优化与扩张规划，持续净负会破坏 reward loop。

### D6: `recovery_pow.enabled` 默认开启还是默认关闭

- **背景**: DSV4 Security 指出 recovery PoW 默认关闭时，分布式攻击可绕过 per-IP 限流进行恢复凭据爆破；但默认开启涉及 onboarding/移动端 UX。
- **方案A: 默认开启低难度 PoW（如 16-bit）** — **推荐**
  - 生产默认开启，低风险开发环境可关闭。
  - 优点：为恢复路径增加基础成本层；与 CSR PoW 多层 admission 思路一致。
  - 缺点：移动端/低性能设备有少量延迟，需要 UX 文案。
- **方案B: 默认关闭，仅依赖 rate limit / ASN / lockout** — **不推荐**
  - 保持恢复流程最快。
  - 优点：用户体验最简单。
  - 缺点：分布式攻击成本低，且与安全文档“PoW 是成本层但不替代限流”的总体哲学不一致。
- **Speaker 推荐**: A。理由：恢复路径是高价值攻击面，低难度 PoW 默认开启的 UX 成本可控，安全收益明确。

### D7: Controller repair 多 Controller 是否提供边际收益

- **背景**: DSV4 Economy 指出当前公式 `min(0.5, controller_count * 0.5)` 在 controller_count ≥ 1 时恒为 0.5，意味着第二个 Controller 后无收益，但文档未说明是否为目标设计。
- **方案A: 明确多 Controller 不增加 repair 上限** — **可接受**
  - 公式简化为“只要拥有至少一个 Controller，每 tick age 回退上限固定 0.5”。
  - 优点：反雪球强，避免多 Controller 堆叠形成无敌维修。
  - 缺点：多 Controller 的经济/战略价值降低，需要其他收益支撑。
- **方案B: 提供小幅阶梯式边际收益** — **Speaker 推荐**
  - 例如 `min(1.0, 0.3 + controller_count × 0.1)` 或类似递减收益。
  - 优点：多 Controller 有可感知价值，但仍有限制；更符合扩张奖励。
  - 缺点：需 balance 验证，可能增强防守。
- **Speaker 推荐**: B。理由：完全无边际收益容易误导且削弱扩张目标；小幅递减收益更符合策略直觉。

### D8: WASM 输出超过 256KB 是整批丢弃还是尝试截断/保留前缀

- **背景**: B8 显示预算表写截断前 256KB，但 determinism/sandbox/validation 更倾向整批丢弃。此项影响玩家体验与安全确定性。
- **方案A: 整批丢弃，不解析任何前缀** — **推荐**
  - 记录 `output_truncated` / `TickValidationFailed`，不保留 partial command，不退款或按既定 validation refund 规则处理。
  - 优点：确定性强，避免 UTF-8/JSON/parser prefix 分叉和边界攻击。
  - 缺点：单个超限输出会损失同 tick 其他合法 commands，玩家体验较硬。
- **方案B: 截断并尝试保留可解析前缀** — **不推荐**
  - 解析前 256KB 中完整 JSON/command prefix。
  - 优点：玩家体验更宽容。
  - 缺点：解析器差异、截断边界攻击、replay 分叉风险高。
- **Speaker 推荐**: A。理由：WASM 输出是 replay-critical 输入，确定性与安全应优先于宽容。

## 总结

R31 的主要问题不是方向错误，而是 clean-slate 文档仍混有旧阶段语义、手写派生表、未裁决参数和互相覆盖的权威合同。下一轮修复应优先采用“权威源唯一化 + 机器校验 + 删除相反语义”的策略，而不是在各文档局部补丁式解释。

推荐修复顺序：

1. 先裁决 D1-D8。
2. 按 B1/B2/B3/B5 收敛跨文档权威合同。
3. 按 B4/B6/B8 补齐 gameplay/economy/determinism 可实施细节。
4. 清理全部 MVP/Tier/Future/Phase/Rxx 叙事。
5. 增加 IDL/docs consistency CI，确保下一轮不再出现同类漂移。

---

## D-items 裁决记录（2026-06-21）

| ID | 裁决 | 详情 |
|----|------|------|
| D1 | **A — 全局 tick 原子** | room-partition 仅为 FDB 写入优化；任一 failure → tick abandon + global snapshot restore + retry。删除 best-effort/local 推进语义 |
| D2 | **A — 8 种全核心** | Leech/Fabricate 与其余 6 种同级，删除 Tier 2 标记，补齐 validation/R/W/buffer |
| D3 | **A — 拆分双延迟** | `global_deposit_delay=10` + `global_withdraw_delay=100`，均为 world.toml 可配置 |
| D4 | **B — 按 GCL 缩放** | `allied_daily_cap = max(10,000, receiver_gcl × 20,000)`，world mode multiplier 可调 |
| D5 | **A — 早中期正收益** | 1-2 房接近平衡/略正，5-10 房优秀代码可正，20+ 房边际压缩，50 房 soft cap。重算全部 balance sheet |
| D6 | **A — 默认开启低难度 PoW** | Recovery PoW 默认 16-bit，低风险环境可关闭 |
| D7 | **删除 global repair cap** | 物理约束（repair_range、repair_capacity per Controller、drone 分布）已充分自然限制 |
| D8 | **A — 整批丢弃 + 用户警告** | 输出 >256KB → 全部命令作废 + `output_truncated` 通知 + 写入 TickCommitRecord |
