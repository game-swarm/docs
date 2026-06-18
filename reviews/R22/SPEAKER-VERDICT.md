# Swarm 设计评审 R22 — Speaker 共识报告

## 裁决概要

- 本轮总览：R22 是 7 方向 × 2 模型的两级阅读评审轮。Speaker 只综合已有 reviewer 报告，不补跑缺失 reviewer。
- Phase 1 完成情况：12/14 reviewer 报告可读；2/14 缺失。
  - 缺失：`rev-gpt-performance.md`、`rev-gpt-apidx.md`
  - 可读：Architect 2/2、Security 2/2、Designer 2/2、Performance 1/2、Economy 2/2、API/DX 1/2、Determinism 2/2
- Phase 2 补漏情况：本轮未见独立 Phase 2 补充报告；以下 CrossCheck 章节基于 Phase 1 reviewer 的跨方向提示综合。
- 收敛评估：文档/设计已具备较强的架构骨架，但 R22 仍出现多项跨方向、跨模型重复发现的 contract conflict，尤其集中在 persistence/TickTrace/deploy 状态机、经济权威源、special attack 调度、IDL/API 生成链、快照/容量/性能预算。
- Freeze 状态：不建议 Freeze；R23 前必须先闭合共识 Blocker 与若干高优先级设计决策。

## 总体 Verdict

REQUEST_MAJOR_CHANGES

理由：12 份可用报告中，3 份明确 REQUEST_MAJOR_CHANGES（gpt-economy、dsv4-economy、gpt-determinism），9 份 CONDITIONAL_APPROVE，0 份 APPROVE。多个 Critical/High 由至少 2 个方向和至少 2 个模型交叉发现，已经超出单方向 polish 范围，属于进入实现前必须统一的设计/规范合同问题。

## 共识 Blocker（跨方向 + 跨模型同意）

### B1: Persistence / TickTrace / Object Store / Deploy 的 replay-critical 状态机不闭合

**方向 × 模型矩阵**:
- Architect × GPT：A1 Critical — Persistence / TickTrace 审计合同互相冲突；CrossCheck CX1 指向 Security
- Determinism × GPT：T1 Critical — TickTrace 原子性与 Persistence async blob 合同互相冲突；CX1/CX2 指向 Architect/Reliability
- Security × GPT：H3 High — 部署对象存储异步流程存在 TOCTOU 与激活前可用性缺口；CX2 指向 Architect
- Architect × DeepSeek：CX3 指出 `swarm_deploy` deploy_mutation replay class 与 blob async upload / FDB manifest commit 之间存在 replay window
- Designer × DeepSeek：CX1 指出 deploy_mutation flow 可能导致部分部署模块被 tick boundary 激活
- Determinism × DeepSeek：RG2 指出 FDB commit failure + object store async gap；CrossCheck CX2 指出 canonical replay-critical 规格可能不存在

**问题**：多份文档同时声明 TickTrace、FDB commit、object store blob、deploy activation、audit/replay completeness，但没有单一状态机定义 replay-critical subset 与 debug/rich blob 的边界。当前文本允许“manifest 已提交但 blob pending/failed”的状态，却没有定义下一 tick 是否激活、replay verifier 缺 blob 时如何处理、tick success/failure 是否回滚、反作弊审计是否仍完整。

**修正要求**：
1. 选择并写明权威模型：建议采用 “FDB 小事务原子提交 replay-critical subset；object store 仅承载非关键 debug/rich trace blob”。
2. 为 deploy 写完整状态机：validate → upload/prepare → manifest commit → activation eligibility → tick boundary activation → failure/rollback/retry。
3. 明确 replay-critical 字段必须包含：commands/rejections、state_checksum、system_manifest_hash、world_config_hash、mods_lock_hash、fuel ledger、terminal_state、canonical_codec_version、deploy activation decision。
4. 明确 object store blob missing 时 replay 行为：不能影响 deterministic replay；只能降级 rich audit，并必须产生可审计 alert。
5. 将 `deploy_mutation` replay class、Persistence Contract、Tick Protocol、API Registry 的相关段落统一到同一状态机引用。

### B2: 经济系统权威源分叉，Resource Ledger / economy IDL / API Registry 给出互斥模型

**方向 × 模型矩阵**:
- Economy × GPT：E1 Critical 经济权威源冲突；E2 Critical 存储税两套阈值；E5/E6 High global transfer / AlliedTransfer 冲突
- Economy × DeepSeek：C1 Critical Storage tax tier incompatible；C2 Critical UpkeepDeduction incompatible；H2 AlliedTransfer contradiction
- API/DX × DeepSeek：world.toml schema missing、Refund policy ambiguity、primitive/entity types 与 registry 缝隙；CrossCheck CX3 指向 Game Designer/Architect
- Architect × DeepSeek：D6 Refund 表 `InsufficientResource` 重复且矛盾
- Designer × GPT/DeepSeek：PvE/economy 边界与玩法承诺冲突，PVE drop/economy incentives 需重新界定

**问题**：经济系统的机器权威源不清。Storage tax 同时存在 percentage tiers 与 absolute thresholds；UpkeepDeduction 同时存在 per-structure/controller-level 与 superlinear per-room/empire formula；AlliedTransfer 同时被描述为 tax-free/no cooldown 与 200bp fee + 500 tick cooldown；Recycle/Refund/Build/Lockup 语义也有重复定义。实现者无法判断 IDL、Resource Ledger、API Registry 哪一份是 source of truth。

**修正要求**：
1. 明确经济权威链：建议 `resource-ledger.md` / `economy.idl.yaml` 为源，`api-registry.md` 为生成产物，不允许手写分叉。
2. 统一 storage tax 表示：推荐 percentage-based tiers，并由 codegen 转为 UI/API 展示。
3. 统一 UpkeepDeduction：采用 superlinear empire upkeep 模型或明确选择 per-structure 模型，删除另一套。
4. 统一 AlliedTransfer：fee、delay、cooldown、daily cap、alliance override 必须有单一默认值与 mode override 规则。
5. 为 Recycle/Refund/Lockup/Build 资源流写 single-entry ledger transaction 表，标明 faucet/sink/transfer/lockup 与 refund rules。
6. 补全 `world.toml`/world_config schema：经济参数必须有类型、默认值、范围、mode override 与 JSON Schema/IDL 生成入口。

### B3: Special Attack / Status 调度模型存在跨文件冲突，单 writer 与并行 reducer 边界不清

**方向 × 模型矩阵**:
- Architect × GPT：A3 High — 特殊攻击调度模型不闭合
- Determinism × GPT：T4 High — Phase 2b special attack / status schedule 内部矛盾
- Architect × DeepSeek：D1 Critical — `02-command-validation §3.19` 与 manifest 系统排序冲突；CX4 指出 parallel set 写 `pending_intents` 的并发策略未定义
- Designer × GPT：G6 Medium — 特殊攻击体系过早进入 Standard 会压垮可读性
- Designer × DeepSeek：G3 Medium — Novice 禁用 special attack 导致体验断崖

**问题**：文档同时把特殊攻击描述为 Phase 2a intent、combat parallel set、status reducer、status_advance_system 或 S22 应用，缺少单一的写入者、buffer、排序、冲突解决和状态推进顺序。并行写 `pending_intents` 的 determinism 和 data race 约束没有明示。

**修正要求**：
1. 写一张特殊攻击执行表：intent collect → canonical sort → reducer resolve → state write → status advance → damage/application。
2. 指定每个 status/component 的唯一 writer system_id，禁止多路径写状态。
3. 定义 `pending_intents` 的并发写入结构：per-system/per-thread sub-buffer + merge sort，或 serial collector；不可依赖 nondeterministic push order。
4. 明确 Novice/Standard/Arena 的 special attack 解锁策略，避免 gameplay 与 technical schedule 分叉。
5. 将 manifest、command-validation、gameplay、API action schema 统一引用此表。

### B4: IDL/API Registry/接口文档生成链未形成单一事实源，导致命令、工具、host function、常量多处漂移

**方向 × 模型矩阵**:
- API/DX × DeepSeek：C1 object_id missing from IDL；C2 host_get_terrain signature mismatch；H1 CommandAction 19 vs 21；H2 MCP tool count 54 vs 56
- Security × GPT：H2 MCP 工具清单不一致，可能造成未审计端点或权限绕过
- Architect × GPT：A2 High 单一权威源被多个文件重复声明并产生分叉
- Architect × DeepSeek：D2 High MAX_DRONES_PER_PLAYER 50 vs 500
- Designer × GPT：CX1 指出 MCP tool 数量多处冲突影响 AI onboarding 文档可信度
- Economy × DeepSeek/GPT：Body part cost、AlliedTransfer、storage tax、Upkeep 等均怀疑 IDL → registry generation stale

**问题**：IDL-first 是本轮公认优点，但实际文档仍大量手写重复：CommandAction 参数、host function signature、tool count、MAX_DRONES_PER_PLAYER、body part cost、error codes、refund table、MCP resource/tool 数量等出现漂移。实现者可能按不同文件实现出不兼容协议。

**修正要求**：
1. 建立并记录 codegen pipeline：输入文件、生成目标、不可手写区域、CI diff check。
2. IDL 补齐 CommandAction 基础字段与 primitive ID types；确认 `object_id` 是否所有 action 必需，或拆分 per-action schema。
3. 统一 host function canonical source，尤其 `host_get_terrain` 签名；SDK wrapper 可以提供友好重载，但 ABI 必须唯一。
4. 修正 MCP tool count / CommandAction count / auth tool count，并禁止非生成文件手写计数。
5. 为关键常量建立 source-of-truth 表：drone cap、WASM size、storage cap、body costs、refund rates、rate limits。
6. CI 应扫描非权威文件中的关键常量或代码块，防止 stale duplicate。

### B5: Capacity / snapshot / worker/FDB 性能合同过于乐观，且会反馈到 gameplay 与 determinism

**方向 × 模型矩阵**:
- Performance × DeepSeek：D1 High snapshot truncation cascade；D2 High worker dispatch overhead；D3 High FDB single-commit contention；D4-D7 Medium 容量预算缺口
- Architect × GPT：A6 Medium 容量模型表达过于乐观；CrossCheck CX5 指向 Performance/DevOps
- Architect × DeepSeek：D4 Medium snapshot truncation `distance_to_drone` 歧义；D2 High drone cap 50 vs 500
- Determinism × GPT：T6 Medium truncation 跨文件不一致；T7 active player set/shuffle 输入未定义
- Determinism × DeepSeek：D2 path cache determinism；RG1 truncation amplification
- Designer × DeepSeek：CX2 要求验证 256KB 常量对 500 drones + pressure components 是否足够

**问题**：容量目标（1000 players / 50000 entities / 256KB snapshot / 40 cores / FDB commit）目前像静态承诺，而非 measured admission contract。Snapshot truncation 的优先级、distance function、entity threat priority 与 omitted schema 也不统一。性能退化会改变 active player set、pathfinding budget、snapshot visibility 与 gameplay 公平性，从而影响 replay/determinism。

**修正要求**：
1. 将容量合同改为 measured admission model：基于 recent p95/p99 sandbox、snapshot stitching、FDB commit、network fan-out 动态计算 admitted players/fuel。
2. 定义容量 SLO 与硬 budget：每 tick FDB mutation count、snapshot build time、network broadcast budget、worker reset bandwidth、pathfinding budget。
3. Snapshot Contract 成为唯一权威：bucket order、distance function、多 drone aggregation、critical entity rule、threat/value priority、byte length 计算、omitted schema。
4. Pathfinding cache 必须被定义为 pure optimization：hit/miss 不改变输出；budget/fuel accounting 与 cache population timing replay-critical 或明确排除。
5. 对 50 vs 500 drone cap 做设计裁决，并重新评估 snapshot 与 worker pool 预算。

## CrossCheck 跨方向发现

本轮没有独立 Phase 2 补漏报告；以下为 Phase 1 CrossCheck 聚类结果。

### CX1: Deploy / object store / replay gap
**来源**：gpt-architect、dsv4-architect、gpt-security、dsv4-designer、gpt-determinism、dsv4-determinism
**目标方向**：Architect / Security / Determinism
**发现**：async blob upload、FDB manifest commit、next-tick activation 与 replay verifier 的状态机缺口被多方向重复指出。
**处置**：升级为 Blocker B1。

### CX2: IDL/API/tool count/host function/常量生成链漂移
**来源**：dsv4-apidx、gpt-security、gpt-designer、gpt-economy、dsv4-economy、dsv4-architect
**目标方向**：Architect / API-DX
**发现**：MCP tool count、CommandAction count、host_get_terrain、MAX_DRONES_PER_PLAYER、body part cost、AlliedTransfer、storage tax 等出现多处漂移。
**处置**：升级为 Blocker B4；经济部分并入 B2。

### CX3: Special attack schedule 与 status lifecycle
**来源**：gpt-architect、gpt-determinism、dsv4-architect、gpt-designer、dsv4-designer
**目标方向**：Architect / Gameplay / Determinism
**发现**：特殊攻击到底在哪个 phase 收集、排序、reducer、推进状态不统一；并行 buffer 写入未定义。
**处置**：升级为 Blocker B3。

### CX4: Snapshot truncation / visibility / debug hints 可能形成 gameplay 与 oracle 风险
**来源**：gpt-architect、dsv4-performance、dsv4-security、gpt-security、dsv4-designer、gpt-determinism
**目标方向**：Architect / Security / Designer / Performance
**发现**：snapshot truncation priority、critical entity、threat weight、debug_detail/practice hint、omitted_count schema、visibility_filter 需要统一，否则既影响游戏策略又可能泄露不可见实体。
**处置**：部分并入 B5；security/redaction 部分列为 S-H2。

### CX5: Pathfinding budget/cache fairness 与 determinism
**来源**：dsv4-security、dsv4-performance、dsv4-determinism、gpt-determinism
**目标方向**：Architect / Determinism / Performance
**发现**：先到先得预算可被利用；cache hit/miss、cache population timing、terrain invalidation 可能影响 fuel/output。
**处置**：并入 B5；具体实现约束列为 T-H2/P-H4。

### CX6: Gameplay onboarding / replay / spectator / product slicing
**来源**：gpt-designer、dsv4-designer、gpt-security
**目标方向**：Designer / Architect / Security
**发现**：第一小时体验、AI 自学课程包、Replay/观战/社区传播、Arena 排名/赛季边界、replay privacy 与 public_spectate 的产品层级不统一。
**处置**：记录为 Designer High 与 Security Medium；不升为本轮架构 Blocker，但 R23 前应完成产品切片。

## 方向专属 High 优先级

### A-H1: Room / Controller / Entity lifecycle 状态机仍不完整
来源：gpt-architect A4、gpt-determinism T5、dsv4-determinism D3/FS1。Entity creation 可见性、SpawningGrace 边界、contested room tiebreak、controller repair/aging 需要完整 transition table。

### A-H2: 权威源治理不足
来源：gpt-architect A2、dsv4-architect D2/D3。需要为 limits、rejection enum、command schema、snapshot truncation、system order、persistence semantics、sandbox budgets 指定唯一 owner。

### S-H1: CSR challenge / Auth API / token semantics 冲突
来源：dsv4-security C1、gpt-security H1。CSR challenge 字段传递矛盾可能导致 PoW/CSR 绕过；API Registry 的 token-first 语义可能削弱 certificate + canonical request signature 模型。

### S-H2: Browser / Agent / Admin / transport 边界混杂
来源：gpt-security H4/H5、dsv4-security H3/M1/L1。Browser endpoint、Agent endpoint、CLI/WebSocket audience、Admin break-glass、username_visibility、canonical timestamp 单位需要统一，避免跨协议混淆与权限扩大。

### S-H3: WASM sandbox profile 前后不一致
来源：dsv4-security H1/H2、gpt-security M1/M2/M3、gpt-determinism T8。Store reset 验证、seccomp write vs cgroup wbps=0、Wasmtime version/SIMD/floating point、module size cap 需要形成可 CI 验证的 runtime profile。

### D-H1: 第一小时与 AI onboarding 缺少可执行课程包
来源：gpt-designer G1/G2。设计承诺“AI 可通过 MCP resources 学会怎么玩”，但缺少 machine-readable curriculum、starter bot、schema/docs/sdk/hash、错误修复路径。

### D-H2: Replay/观战/社区传播 MVP vs RFC 边界冲突
来源：gpt-designer G3/G4、gpt-security M5。需要拆分本地 replay、分享 replay、观战、公开 replay、Arena leaderboard/season/circuit 的优先级与隐私默认值。

### D-H3: Movement / body part / special attack 学习曲线与策略深度需要再平衡
来源：dsv4-designer G1/G2/G3、gpt-designer G6。4-direction movement、body irreversibility、Novice 禁用 special attacks 与 Standard 复杂度跳跃影响可读性与实验成本。

### P-H1: Snapshot truncation cascade under adversarial entity spam
来源：dsv4-performance D1。需要 density tax / threat-aware priority / room-level entity pressure budget，防止可见实体 spam 使关键敌方威胁被截断。

### P-H2: Worker pool dispatch overhead 与 40-core/1000-player 推导过于乐观
来源：dsv4-performance D2、gpt-architect A6。需要 measured admission、dispatch overhead、reset bandwidth、slow-player isolation。

### P-H3: FDB single-commit contention at 50000 entities
来源：dsv4-performance D3。需要 per-tick mutation budget、batch/defer rules、CI load simulation。

### E-H1: 收支平衡表显示 Standard 全场景长期净亏损
来源：gpt-economy E4、dsv4-economy H1。需要初始资源包、RCL progression timeline、breakeven point、source distribution model，否则最优策略可能是“不扩张”。

### E-H2: Upkeep deficit death spiral 与 recovery path 缺失
来源：dsv4-economy H3、gpt-economy E3/E4。维护费不足导致效率下降，效率下降又导致更缺资源；需定义 forgiveness/decay/minimum subsistence income。

### E-H3: Global transfer / AlliedTransfer / No Teleport 约束冲突
来源：gpt-economy E5/E6、dsv4-economy H2。需要明确普通 transfer、allied transfer、market transfer 的 fee/delay/cooldown/cap 与 UI 展示。

### X-H1: CommandAction / MCP / host ABI critical gaps
来源：dsv4-apidx C1/C2/H1/H2。`object_id`、`host_get_terrain`、CommandAction count、MCP tool count 是 API Freeze 前必须修正的机器接口问题。

### X-H2: API version negotiation 与 primitive type registry 不完整
来源：dsv4-apidx M2/M3。需要 `api_version` handshake、VersionMismatch、primitive ID type encoding/serialization/range。

### T-H1: Canonical serialization / command_hash 未闭合
来源：gpt-determinism T3、dsv4-determinism D1。必须定义 CanonicalCommandV1 或 RFC8785/JCS，明确 hash 输入字段集合、unicode/key order/integer/fixed-point/time encoding。

### T-H2: RNG stream / host RNG / path cache determinism 不闭合
来源：gpt-determinism T2、dsv4-determinism D2/CX5。需要 RNG domain table、seed_material、stream_id、draw index rule；path cache 不得影响输出或必须进入 replay-critical envelope。

## Medium/Low 处置

| ID | 问题 | 来源方向 | 处置 |
|----|------|---------|------|
| M1 | Snapshot `omitted_count` / omitted schema 整数 vs 分桶字符串不一致 | Security / Architect / Determinism | 并入 Snapshot Contract 修正，R23 前统一 |
| M2 | Canonical Request / WebSocket timestamp 单位不一致 | Security | 与 Auth API 修正一并统一为 `unix_ms` 或明确字段名 |
| M3 | Debug detail / rejection_detail / visibility redaction 关系不清 | API/DX / Security | 定义 wire field 与 human debug field；practice hint 必须走 redaction policy |
| M4 | RuleMod capability whitelist 缺少数值边界 | Security / Designer | 作为 world_config schema 的一部分补全 capability constraints |
| M5 | CodeSigningCertificate 180 天 TTL 权衡未裁决 | Security | D-item 或安全默认值：建议 30/90 天 + automation renewal |
| M6 | Wasmtime critical crate/CVE 列表需自动覆盖依赖 | Security | 改为 cargo audit + wasmtime org dependency policy |
| M7 | Network fan-out budget 缺失 | Performance | 加入 capacity SLO；实现期压测 gate |
| M8 | Reactive admission control 无 hysteresis | Performance | 加 hysteresis band；Low，可随 admission contract 修 |
| M9 | TickTrace WAL write blocking | Performance | 明确 I/O thread/io_uring/timeout 策略；Low |
| M10 | Tutorial recycle/free respec 可能被刷信息 | Economy / Designer | 用 explicit free_respec_count 或 decay refund window |
| M11 | Source quality vs room count 未建模 | Economy | R23 balance sheet 必须引入 source distribution model |
| M12 | PvE budget 与 controller_level 绑定导致 rich-get-richer | Economy / Designer | 推荐改为 zone-based 或 shared PvE budget with diminishing returns |
| M13 | Arena `par_time` 未定义 | Designer | 定义为 designer-set static value；Low |
| M14 | Drone-to-drone communication 缺失 | Designer | MVP 可选 minimal intra-player message；Low |
| M15 | Late-game resource sink gap | Designer | 作为 P1+ Grand Project backlog；Low |
| M16 | IndexMap determinism 依赖插入顺序 | Determinism | 文档说明 + CI invariant；Low |
| M17 | Combat parallel set owner immutability invariant | Determinism | 文档化并加 CI assertion；Low |
| M18 | Global resource cap 达上限后的 faucet clipping 未定义 | Economy / Determinism | 加入 resource ledger deterministic ordering |

## D-items（需用户裁决）

### D1: replay-critical TickTrace 与 object store debug blob 的权威模型

**问题**：当前文档在“每 tick audit 完整性”和“object store async blob”之间摇摆。

**选项**：
- A. 严格 replay 模型：所有 replay-critical subset 必须随 FDB tick transaction 原子提交；object store 只保存非关键 rich trace/debug blob。
- B. 异步审计模型：承认 rich replay/audit 不是每 tick 强保证，tick state deterministic 但 audit best-effort。

**推荐**：A。它保留 deterministic replay 与反作弊闭环，同时允许大体积 blob 异步降级，最符合多位 reviewer 的收敛建议。

### D2: 经济权威源到底是 Resource Ledger 还是 economy IDL/API Registry

**问题**：当前经济公式在 `resource-ledger.md`、`economy.idl.yaml`、`api-registry.md` 之间分叉。

**选项**：
- A. Resource Ledger 是设计/数学权威，economy IDL 是机器 schema，API Registry 全部生成。
- B. economy IDL 是唯一机器权威，Resource Ledger 只保留解释性 prose 与链接。

**推荐**：A/B 混合但层级明确：数学公式以 Resource Ledger 为 authoring source，IDL 引用/编码同一模型，Registry 只生成。关键是禁止 Registry 手写经济数值。

### D3: MAX_DRONES_PER_PLAYER 采用 50 还是 500

**问题**：Architect/API/Performance 多处发现 50 vs 500 冲突；该值直接影响性能预算、snapshot size、repair formula、经济曲线与玩法规模。

**选项**：
- A. MVP/Standard 默认 50，500 作为高容量世界或后续扩展目标。
- B. Standard 默认 500，要求 R23 同步完成 capacity/snapshot/repair/economy 压力模型。

**推荐**：A。先以 50 冻结 MVP，保留 `world.max_drones_per_player` 可配置上限；500 作为经过压测后的 mode override。

### D4: Special Attack 在 Standard 的引入节奏

**问题**：技术调度未闭合，设计侧也认为 Novice 禁用 → Standard 全量启用会造成断崖。

**选项**：
- A. Standard 分阶段解锁 special attacks：基础 Debilitate/Disrupt → advanced Hack/Drain/Overload → mode-specific Fabricate/Leech。
- B. Standard 全量启用，但教程/SDK 强引导。

**推荐**：A。既降低 onboarding 复杂度，也给调度/状态系统分阶段实现空间。

### D5: Arena / Replay / Spectator 的 MVP 范围

**问题**：Replay/观战/社区传播被同时描述为核心与 RFC，Arena 也同时出现“无排名房间制”和“赛季/锦标赛”。

**选项**：
- A. MVP 只保留 local replay + private replay URL；public spectate/leaderboard/season/circuit 延后。
- B. MVP 包含 social replay highlight + delayed public spectator，但 Arena ranked/season 延后。

**推荐**：B。GPT Designer 指出传播面是产品核心，建议保留最小 social replay，但严格默认 delayed/redacted，竞技排名系统延后。

### D6: Storage tax tier 表示方式

**问题**：absolute thresholds 与 percentage tiers 两套模型并存。

**选项**：
- A. percentage-based tiers；根据 capacity 动态计算展示阈值。
- B. absolute thresholds；不同 mode/容量单独配置。

**推荐**：A。更适合可配置 world capacity，也得到 dsv4-economy 明确推荐。

## D-items 裁决结果

| D-item | 决策 | 内容 |
|--------|------|------|
| D1 | **A** | 严格 replay 模型：replay-critical subset 随 FDB tick transaction 原子提交；object store 只保存非关键 debug blob |
| D2 | **A** | Resource Ledger 是设计/数学权威，economy IDL 是机器 schema，API Registry 全部生成，禁止手写经济数值 |
| D3 | **A** | MVP/Standard 默认 50 drones，500 作为高容量 world mode override |
| D4 | **B** | Standard 全量启用 special attacks，通过教程/SDK 强引导降低学习曲线 |
| D5 | **B** | MVP 包含 social replay highlight + delayed public spectator；Arena ranked/season 延后 |
| D6 | **A** | percentage-based storage tax tiers，根据 capacity 动态计算阈值 |

## 文档维护项

1. 创建或补齐 `world_config.idl.yaml` / `world.toml` JSON Schema，覆盖经济、容量、visibility、RuleMod capability、mode override。
2. 建立 `specs/reference/codegen.md`：IDL → API Registry / SDK / docs 的输入输出、不可手写区、CI diff gate。
3. 为关键常量建立 `canonical-limits` 表，并从非权威文件删除重复手写值。
4. 增加 `Canonical Serialization` 规范或引用 RFC8785/JCS，并定义 `CanonicalCommandV1`。
5. 增加 `Replay-Critical TickTrace Contract`，区分 FDB critical subset 与 object-store debug blob。
6. 更新 `ROADMAP.md`：R23 入场前需要先完成 Blocker B1-B5；Performance load test 可作为 implementation gate，但 contract 必须先写清。
7. 更新 reviews index：记录 R22 两份 reviewer 缺失，Speaker verdict 基于 12/14 报告。

## R23 入场条件

R23 reviewer 启动前，至少满足：

1. B1-B5 均有明确文档修正，不再存在互斥合同。
2. 关键 D-items 已由用户裁决并写入对应设计/规范文档。
3. 经济权威链与 codegen pipeline 已写明，API Registry 不再手写漂移数值。
4. TickTrace/deploy/persistence 状态机具备完整 transition table。
5. Special Attack/status schedule 有唯一 writer 与 deterministic reducer 规则。
6. Snapshot/capacity/admission contract 由静态承诺改为 measured SLO + hard budget。
7. 缺失 reviewer（gpt-performance、gpt-apidx）在 R23 必须恢复；R22 不补跑。

## 评审统计

### Verdict 分布矩阵（7×2）

| Direction | GPT-5.5 | DeepSeek V4 Pro |
|-----------|---------|-----------------|
| Architect | CONDITIONAL_APPROVE | CONDITIONAL_APPROVE |
| Security | CONDITIONAL_APPROVE | CONDITIONAL_APPROVE |
| Designer | CONDITIONAL_APPROVE | CONDITIONAL_APPROVE |
| Performance | 缺失 | CONDITIONAL_APPROVE |
| Economy | REQUEST_MAJOR_CHANGES | REQUEST_MAJOR_CHANGES |
| API/DX | 缺失 | CONDITIONAL_APPROVE |
| Determinism | REQUEST_MAJOR_CHANGES | CONDITIONAL_APPROVE |

### Severity 统计（可读报告汇总，按 reviewer 自报）

| Direction/Reviewer | Critical | High | Medium | Low | Verdict |
|--------------------|----------|------|--------|-----|---------|
| gpt-architect | 1 | 3 | 3 | 1 | CONDITIONAL_APPROVE |
| dsv4-architect | 1 | 1 | 2 | 3 | CONDITIONAL_APPROVE |
| gpt-security | 0 | 5 | 7 | 3 | CONDITIONAL_APPROVE |
| dsv4-security | 1 | 3 | 4 | 4 | CONDITIONAL_APPROVE |
| gpt-designer | 0 | 3 | 3 | 2 | CONDITIONAL_APPROVE |
| dsv4-designer | 0 | 0 | 4 | 3 | CONDITIONAL_APPROVE |
| gpt-performance | 缺失 | 缺失 | 缺失 | 缺失 | 缺失 |
| dsv4-performance | 0 | 3 | 4 | 2 | CONDITIONAL_APPROVE |
| gpt-economy | 2 | 4 | 3 | 1 | REQUEST_MAJOR_CHANGES |
| dsv4-economy | 2 | 3 | 4 | 3 | REQUEST_MAJOR_CHANGES |
| gpt-apidx | 缺失 | 缺失 | 缺失 | 缺失 | 缺失 |
| dsv4-apidx | 2 | 2 | 5 | 4 | CONDITIONAL_APPROVE |
| gpt-determinism | 1 | 4 | 4 | 1 | REQUEST_MAJOR_CHANGES |
| dsv4-determinism | 0 | 0 | 3 | 4 | CONDITIONAL_APPROVE |

### 共识强度评估

- 强共识 Blocker：B1、B2、B4。均由 ≥3 方向、≥2 模型重复发现，且包含 Critical/High。
- 中强共识 Blocker：B3、B5。均跨方向重复，但部分 reviewer 将其定为 Medium/High，需以 R23 文档修正关闭。
- 方向性强项：Security 架构、IDL-first 思路、fixed-point/determinism 意识、Resource Ledger skeleton、snapshot truncation 基本思路、WASM sandbox 分层均被多名 reviewer 肯定。
- 主要风险形态：不是“没有设计”，而是“设计分叉太多”。如果不先统一权威源与状态机，进入实现会产生多个互不兼容的正确实现。
