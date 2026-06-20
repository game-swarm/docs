# Swarm 设计评审 R24 — Speaker 共识报告

## 裁决概要

- 本轮性质：Clean Slate 全量 spec ↔ design 对齐检查。
- 流程状态：**BLOCKED / INCOMPLETE**。看板 14 个父任务均已进入 done，但仓库中只有 **10/14** 份可追溯 reviewer 报告；4 份 GPT 报告缺失文件，且父任务结果为空。
- 可用报告：rev-dsv4-architect、rev-dsv4-security、rev-gpt-designer、rev-dsv4-designer、rev-dsv4-performance、rev-dsv4-economy、rev-gpt-apidx、rev-dsv4-apidx、rev-gpt-determinism、rev-dsv4-determinism。
- 缺失报告：rev-gpt-architect、rev-gpt-security、rev-gpt-performance、rev-gpt-economy。对应任务显示多次 `worker exited cleanly (rc=0) without calling kanban_complete or kanban_block`，但未生成 `/data/swarm/docs/reviews/R24/rev-gpt-*.md` artifact。
- Speaker 原则：不补跑缺失 reviewer；以下裁决基于 10 份可读报告形成，并透明标记覆盖缺口。
- Phase 2 补漏情况：本轮任务为全量阅读模式，reviewer 输出未采用 Plan B CrossCheck 桥接；无 Phase 2 补漏任务。

## 总体 Verdict

**REQUEST_MAJOR_CHANGES**

理由：即使只看 10/14 可用报告，也已经出现多个跨方向、跨模型一致的 Critical/High 级 spec ↔ design 不对齐：Host Function ABI、经济数值、tick/snapshot budget、MCP 工具清单、快照截断策略、CodeSigningCertificate/CSR replay 安全语义等。当前文档不能 Freeze；需要先做一次合同清理，再启动下一轮 Closure Verification。

## 共识 Blocker (跨方向 + 跨模型同意)

### B1: Host Function ABI 权威源分裂

**方向 × 模型矩阵**: Architect × DeepSeek；API/DX × GPT；API/DX × DeepSeek；Determinism × DeepSeek；Determinism × GPT（RNG/ABI 相关）；Performance/Architect 间接受影响。

**来源 reviewer + 严重度**:
- rev-dsv4-architect C1 Critical：`host_get_terrain` 签名在 api-registry 与其他文档不一致。
- rev-gpt-apidx X1 Critical：Host Function ABI 在 design、IDL spec 与 API Registry 间不一致。
- rev-dsv4-apidx C2/C3/C4 Critical：`host_get_terrain`、`host_path_find`、`host_get_world_rules` 签名冲突。
- rev-dsv4-determinism D1 Critical、D4 High：`host_get_terrain` 与 `host_path_find` ABI 跨文档冲突。
- rev-gpt-determinism T1 High：WASM deterministic RNG host function 与 host ABI 权威表冲突。

**冲突位置**: design/engine.md、design/interface.md、specs/reference/api-registry.md、specs/reference/host-functions.md、specs/reference/game_api.idl.yaml、相关 core/spec 文档。

**问题**: Host Function ABI 是 WASM sandbox、SDK、API Registry、确定性 replay 的共同合同；当前多个函数的参数集合、返回值语义、是否带 `rule_id`/`opts`/坐标参数不一致，导致实现者无法判断哪个文档是权威。

**修正要求**:
1. 指定唯一权威源：建议以 `specs/reference/api-registry.md` 或 `specs/reference/host-functions.md` + IDL 作为 canonical source，并在 design 中只保留概念说明。
2. 一次性统一 `host_get_terrain`、`host_path_find`、`host_get_world_rules`、deterministic RNG host function 的签名、返回值、budget、错误码。
3. 为所有 host function 增加 generated/canonical 校验表，禁止手写 count 与 IDL drift。

### B2: 经济与 gameplay 数值合同大面积漂移

**方向 × 模型矩阵**: Economy × DeepSeek；Designer × DeepSeek；Designer × GPT；API/DX × DeepSeek；Performance × DeepSeek（drone cap）。

**来源 reviewer + 严重度**:
- rev-dsv4-economy C1 Critical：building cost 在 `economy.idl.yaml` 与 `design/gameplay.md` 全面不一致。
- rev-dsv4-economy C2 Critical；rev-dsv4-designer C1 Critical：`global_transfer_delay` 10/5/100 tick 多版本冲突。
- rev-dsv4-economy C3 Critical；rev-dsv4-apidx M1 Medium：Recycle refund flat 50% vs lifespan-proportional。
- rev-dsv4-economy C4 Critical；rev-dsv4-designer H3 High；rev-dsv4-apidx H4 High：RangedAttack cost 100 vs 150。
- rev-dsv4-performance C1 Critical：Per-player drone cap IDL=500 vs design/registry=50。
- rev-gpt-designer G4 Medium：Tutorial/Golden Path 默认资源与 starting resources 不对齐。

**冲突位置**: design/gameplay.md、specs/reference/economy.idl.yaml、specs/reference/api-registry.md、specs/reference/game_api.idl.yaml、specs/gameplay/06-feedback-loop.md、08-api-idl 相关文档。

**问题**: 经济合同是玩家策略、AI onboarding、benchmark、balance 与 API validation 的共同基础；当前成本、delay、refund、cap 多处冲突，会直接改变开局节奏、建筑优先级、远程战斗成本与扩张上限。

**修正要求**:
1. 建立 `economy-balance-sheet` 或等价权威表，集中定义 building cost、body part cost、resource transfer、recycle refund、starting resources、drone cap。
2. 将 IDL、api-registry、design/gameplay、tutorial 示例全部改为引用同一权威表。
3. 对 `global_transfer_delay`、RangedAttack cost、Recycle refund、per-player drone cap 做 Closure Verification。

### B3: Tick / EXECUTE / SNAPSHOT 性能预算互相矛盾

**方向 × 模型矩阵**: Architect × DeepSeek；Performance × DeepSeek；Security × DeepSeek；Determinism × DeepSeek；Determinism × GPT。

**来源 reviewer + 严重度**:
- rev-dsv4-architect C2 Critical：EXECUTE budget 400ms vs 500ms。
- rev-dsv4-performance C2 Critical：Snapshot Build 50ms p99 vs 200ms p95。
- rev-dsv4-performance C3 Critical：EXECUTE budget 400ms vs 500ms。
- rev-dsv4-performance H1 High：tick budget sum exceeds tick interval。
- rev-dsv4-security H3 High：Arena 独立预算在 tick protocol spec 中缺失。
- rev-dsv4-determinism D6 Medium；rev-gpt-determinism T4 Medium：snapshot build/truncation 与核心 tick spec 不一致。

**冲突位置**: design/engine.md、specs/core/tick-protocol 相关文档、specs/reference/snapshot-contract、Arena budget 表、benchmark gates。

**问题**: tick budget 是实时性、determinism、worker pool sizing、Arena 公平性的共同合同；当前 EXECUTE 与 SNAPSHOT 的数值、percentile、模式差异、sum constraint 未对齐。

**修正要求**:
1. 建立唯一 tick budget table，区分 World/Arena、COLLECT/EXECUTE/SNAPSHOT/COMMIT/STITCHING。
2. 统一 400ms vs 500ms、50ms p99 vs 200ms p95，并说明 benchmark gate 如何验证。
3. 明确 budget sum 不得超过 tick interval；若允许超额，必须定义 backpressure/degradation 策略。

### B4: MCP / API Registry / Security spec 对 active tools 的状态不一致

**方向 × 模型矩阵**: API/DX × GPT；API/DX × DeepSeek；Architect × DeepSeek；Designer × GPT；Designer × DeepSeek。

**来源 reviewer + 严重度**:
- rev-gpt-apidx X2 High：MCP 工具数量与活跃工具清单漂移。
- rev-gpt-apidx X3 High：security spec 把 Registry 中仍存在的工具标为“已移除”。
- rev-dsv4-apidx H2 High：api-registry MCP 工具计数 54 vs 56。
- rev-dsv4-architect H1 High：MCP 工具计数矛盾 56 vs 54。
- rev-gpt-designer G1 High：AI onboarding 三件套在 security spec 中被标为已移除。
- rev-dsv4-designer M3 Medium：World 无排行榜但 API 提供 leaderboard 工具。

**冲突位置**: design/interface.md、specs/security/03-mcp-security.md、specs/reference/api-registry.md、specs/reference/mcp-tools.md、specs/gameplay/06-feedback-loop.md、design/modes.md。

**问题**: MCP 是 AI/human 管理、onboarding、deploy/debug 的入口；当前 security spec 与 Registry 对 `swarm_get_docs`、`swarm_get_schema`、`swarm_get_available_actions`、`swarm_explain_last_tick`、leaderboard 等工具的 active/removed 状态冲突，可能直接破坏 AI onboarding 与 API/DX。

**修正要求**:
1. 以 API Registry/MCP tools canonical list 为准，删除 security spec 中“已移除但仍 active”的错误描述。
2. 统一工具总数，禁止 intro/table/generated count 不一致。
3. 对 onboarding tools 采用 scope/rate/detail-level 限制，而不是删除。
4. World leaderboard 工具若只属于 Arena 或 analytics，必须在 capability/profile 中限定。

### B5: Snapshot truncation / visibility / determinism 策略存在三套口径

**方向 × 模型矩阵**: Security × DeepSeek；Determinism × DeepSeek；Determinism × GPT；Performance × DeepSeek。

**来源 reviewer + 严重度**:
- rev-dsv4-security H1 High：快照截断优先级桶序不一致。
- rev-dsv4-determinism D3 High：快照截断优先级三套策略冲突。
- rev-gpt-determinism T4 Medium：快照截断唯一权威与核心 tick spec 截断算法不一致。
- rev-dsv4-performance C2 Critical：Snapshot Build budget 冲突。

**冲突位置**: snapshot contract、core tick spec、design/engine.md、security visibility/fog-of-war 相关段落。

**问题**: Snapshot 是 WASM 输入、回放、fog-of-war、公平性与 determinism 的核心边界；截断策略不一致会产生 replay divergence 或信息泄露差异。

**修正要求**:
1. 指定唯一 snapshot truncation algorithm，包括 bucket order、tie-breaker、size limit、debug output、fog-of-war invariant。
2. 所有 tick/snapshot/security 文档引用同一算法。
3. 将预算与截断行为联动：当超预算或超 size 时必须 deterministic degrade。

### B6: Auth / certificate / replay 安全合同内部矛盾

**方向 × 模型矩阵**: Security × DeepSeek；API/DX × GPT（deploy schema）；API/DX × DeepSeek（error/model drift）。

**来源 reviewer + 严重度**:
- rev-dsv4-security C1 Critical：CSR Replay Class 内部矛盾，`swarm_submit_csr` 同时被标为 idempotent 与 non-idempotent。
- rev-dsv4-security C2 Critical：CodeSigningCertificate TTL 出现三组冲突数值。
- rev-dsv4-security H4 High：Refresh Token Grace 并发语义未指定。
- rev-dsv4-security H5 High：联邦 CRL fallback/trust boundary 模糊。
- rev-dsv4-security H6 High：Admin 双签要求跨文档粒度不一致。
- rev-gpt-apidx X4 High：`swarm_deploy` schema 在 security spec 与 Registry/design 不一致。

**冲突位置**: design/auth.md、specs/security/*、specs/reference/api-registry.md、deploy schema 相关段落。

**问题**: auth/security 文档内部和 API schema 的漂移会导致防重放、证书生命周期、deploy 授权与 admin 操作边界不可实现或实现不一致。

**修正要求**:
1. 修正 `swarm_submit_csr` replay class，以 FDB transaction challenge consumption 或 Dragonfly nonce 之一为权威。
2. 统一 CodeSigningCertificate TTL，并同步所有表格、流程图、默认配置。
3. 明确 refresh token grace 的并发语义、CRL timeout fallback、admin dual-sign scope。
4. 将 `swarm_deploy` schema 对齐到 API Registry canonical definition。

## CrossCheck 补漏发现（基于 Phase 2）

无补漏发现。本轮没有 Phase 2 CrossCheck 补充任务；所有 findings 来自全量 clean-slate reviewer 报告。

## 方向专属 High 优先级

### A-H1: Worker Pool / Keyframe / storage ownership contract 未完整进入核心 spec

**来源 reviewer + 严重度**: rev-dsv4-architect C3 Critical、H2 High、M3 Medium。

**冲突位置**: design/engine.md vs persistence/keyframe/core specs。

**问题描述**: Keyframe 存储层归属 FDB vs Keyframe Store 不一致；Worker Pool 参数在核心 spec 缺失；tick budget table 缺少 SNAPSHOT 分项。

**修正建议**: 将 Keyframe Store ownership、Worker Pool sizing、SNAPSHOT budget 纳入核心架构合同，并从 design 中引用。

### S-H1: Worker lifecycle / sandbox / trust fallback 的安全语义缺口

**来源 reviewer + 严重度**: rev-dsv4-security H2/H4/H5/H6 High。

**冲突位置**: sandbox spec、auth spec、federation/CRL/admin sections。

**问题描述**: 1000-tick worker replacement、refresh grace race、CRL fallback、admin dual-sign scope 在安全合同中未能给出实现级语义。

**修正建议**: 将这些项从说明性文字提升为 normative spec；定义失败模式、并发处理、审计事件与默认拒绝策略。

### D-H1: Arena / World 产品模型边界不清

**来源 reviewer + 严重度**: rev-gpt-designer G2 High；rev-dsv4-designer M3 Medium。

**冲突位置**: design/modes.md、API/Registry tournament/leaderboard tools、feedback-loop spec。

**问题描述**: design 将 Arena 描述为房间制/对局制，spec/API 偏向锦标赛制；World 模式声明无排行榜但存在 leaderboard/API 暴露。

**修正建议**: 将 Arena Room、Tournament、Leaderboard 明确分层；World 默认无 competitive leaderboard，仅保留可选 analytics 或 private stats。

### P-H1: Benchmark gates 与预算声明缺少直接绑定

**来源 reviewer + 严重度**: rev-dsv4-performance H2/H3 High。

**冲突位置**: engine budget、benchmark gate、worker pool sizing、snapshot stitching。

**问题描述**: 文档声明预算目标，但 benchmark gates 未直接验证这些目标；worker pool sizing 未计入 snapshot stitching overhead。

**修正建议**: 为每个 budget claim 添加 gate 名称、指标、percentile、target、failure action；将 stitching 纳入 worker sizing 公式。

### E-H1: Future / missing structures 与 Controller repair 经济模型分裂

**来源 reviewer + 严重度**: rev-dsv4-economy H1/H2 High。

**冲突位置**: economy.idl.yaml、design/gameplay.md、resource-ledger。

**问题描述**: 建筑类型集合、future structures、Controller repair hard cap vs distance_decay/repair_cap 分裂。

**修正建议**: 明确 Vanilla P0 结构集合与 future-only 扩展集合；Controller repair 只保留一个公式与 cap 语义。

### X-H1: IDL / CommandAction / RejectionReason canonical model 漂移

**来源 reviewer + 严重度**: rev-dsv4-apidx C1/H1/H3 High；rev-gpt-apidx X5 Medium。

**冲突位置**: game_api.idl.yaml、api-registry.md、codegen.md、commands.md。

**问题描述**: CommandAction count 19 vs 21、`object_id` 参数缺失、RejectionReason count 79 vs 47，说明 generated/codegen 与 hand-written docs 未同步。

**修正建议**: IDL/codegen 为 canonical；手写文档改为引用生成摘要；CI 检查 count/table drift。

### T-H1: Determinism ordering / seed / f64 残留仍未完全闭合

**来源 reviewer + 严重度**: rev-gpt-determinism T2/T3/T5 High/Medium；rev-dsv4-determinism D2/D8/D9/D11/D12 Medium/Low。

**冲突位置**: world_seed rotation、command ordering、ECS ordering、world rules examples、snapshot debug output。

**问题描述**: `world_seed` 轮换语义、命令排序键、ECS host query ordering、path_find cache key、f64 debug/example 残留仍会影响 replay/consensus 精度。

**修正建议**: 统一 seed domain separation、command sort key 五元组、host query ordering、cache key；所有 numeric examples 改为 fixed-point/integer。

## Medium/Low 处置

| ID | 问题 | 来源方向 | 处置 |
|----|------|----------|------|
| ML-1 | `host_get_terrain` 输出大小 4 bytes vs 8KB | Architect | 并入 B1，作为 ABI return contract 子项 |
| ML-2 | Keyframe K 值、SNAPSHOT build tracking、COLLECT ≤/= 2500ms | Architect/Performance | 并入 B3/A-H1，Closure Verification 检查 |
| ML-3 | Heal range 与 Heal 缩短负面状态能力缺失 | Designer | 作为 gameplay/spec 对齐 Medium，修正文档即可 |
| ML-4 | Tutorial / Golden Path starting resources 不一致 | Designer | 并入 B2；更新 tutorial 示例 |
| ML-5 | Feedback-loop Arena 胜利条件与 modes 不一致 | Designer | 并入 D1 或 Arena 模式整理 |
| ML-6 | PoW 难度配置分散 | Security | 文档维护项：集中 default config table |
| ML-7 | Audience 字段模板命名不一致、Auth MCP scope 粒度不一致 | Security | API/security cleanup；非单独 blocker |
| ML-8 | AlliedTransfer、ApiVersion、resource operation 命名边界 | Economy/API-DX | 纳入 economy/API registry cleanup |
| ML-9 | `swarm_simulate` 跨玩家确定性歧义 | Determinism | 明确 simulation isolation 与 seed source |
| ML-10 | Overload 受害者信息不对称 | Security/Designer | 若为有意设计，补充 design rationale |

## 跨方向矛盾

### CFX1: Security spec 的“已移除工具”与 API/DX、Designer 的 onboarding 目标冲突

**来源**: rev-gpt-apidx X3、rev-gpt-designer G1、rev-dsv4-apidx H2、rev-dsv4-architect H1。

**矛盾**: security spec 试图收紧/移除 onboarding/debug tools；API Registry 与 gameplay onboarding 依赖这些 tools 存在。

**处置**: 升级为 B4。安全目标通过 scope/rate/detail filtering 实现，不通过删除 AI onboarding tools 实现。

### CFX2: World “无排行榜”设计承诺与 leaderboard API 暴露冲突

**来源**: rev-gpt-designer G3、rev-dsv4-designer M3。

**矛盾**: modes/design 中 World 被定位为非公平、非 competitive persistent sandbox；API/visibility 却暴露 leaderboard 语义，容易把 Arena 竞争逻辑污染到 World。

**处置**: Medium/High 边界项；需用户确认 World 是否允许非竞争型统计榜或完全禁用公开 leaderboard。

### CFX3: Performance budget 与 Determinism truncation 的权威冲突

**来源**: rev-dsv4-performance C2/H1、rev-dsv4-determinism D3/D6、rev-gpt-determinism T4、rev-dsv4-security H1。

**矛盾**: performance 文档以预算/percentile 描述 snapshot；determinism/security 文档以截断策略描述 snapshot；三套策略未绑定，可能各自实现。

**处置**: 升级为 B3+B5；建立 single snapshot contract。

### CFX4: Economy IDL 与 Game Design 对同一玩法成本给出不同策略空间

**来源**: rev-dsv4-economy C1/C2/C4、rev-dsv4-designer C1/H2/H3、rev-gpt-designer G4。

**矛盾**: design/gameplay 承诺的 early-game pacing 与 IDL/spec 实际成本不同；AI tutorial 与玩家策略会学习到另一套游戏。

**处置**: 升级为 B2；必须先统一 balance sheet 再实现。

## D-items（需用户裁决）

### D1: Arena 是“房间制优先”还是“锦标赛制优先”？

**问题**: design/modes 更像 room-based match；部分 spec/API 更像 tournament/league/leaderboard 管理。两者可以共存，但 P0 权威路径必须明确。

**选项**:
- A：P0 以 Room Match 为主，Tournament/League 为 P1+ 上层编排。
- B：P0 同时支持 Tournament 作为 first-class API，与 Room Match 并列。

**推荐**: A。理由：可降低 P0 API 面与公平性状态机复杂度；Tournament 可由多场 Room Match 组合。

### D2: World leaderboard 是完全禁用，还是允许非竞争型统计？

**问题**: World 模式“不公平且无竞争排行榜”的产品承诺，与 API 中 leaderboard 能力冲突。

**选项**:
- A：World 禁用公开 leaderboard；仅 Arena 暴露 competitive leaderboard。
- B：World 允许非竞争型 stats/analytics，但命名不得叫 leaderboard，且不进入排名奖励。

**推荐**: B。理由：保留社区展示与服务器运营数据，同时避免公平性承诺。

### D3: Recycle refund 采用固定 50% 还是 lifespan-proportional？

**问题**: API/IDL 与 resource-ledger 对 Recycle refund 模型不一致。

**选项**:
- A：固定 50%，简单、易理解。
- B：按 lifespan/damage/remaining value 比例制，经济更稳健。

**推荐**: B。理由：可减少 exploit 与临时建造套利；但需要在 tutorial 中解释。

### D4: Snapshot budget 以 50ms p99 还是 200ms p95 为 P0 gate？

**问题**: performance/design/spec 给出不同 percentile 和目标值。

**选项**:
- A：50ms p99，严格，利于实时体验但实现压力大。
- B：200ms p95，宽松，利于 P0 可达成但尾延迟风险高。

**推荐**: A for Arena，B for World。理由：Arena 需要公平实时性；World 可接受 degrade/backpressure。

## 文档维护项

1. 建立 canonical generated tables：Host Functions、MCP Tools、CommandAction、RejectionReason、Economy Balance、Tick Budget。
2. 将 design 文档中的重复数值改为引用 canonical table，避免手写 drift。
3. 对每个 count/table 增加 CI 或脚本检查：54/56、19/21、79/47 这类漂移不应再由 reviewer 发现。
4. 清理缺失报告对应的 kanban 协议异常：4 个 GPT reviewer 任务被置 done 但 artifact 缺失，后续轮次必须在 Speaker fan-in 前校验文件存在且非空。
5. 下一轮建议不是 clean-slate，而是 Closure Verification：仅验证 B1-B6 + D1-D4 的 closure evidence。

## 评审统计

### 报告完成矩阵

| Direction | GPT-5.5 | DeepSeek V4 Pro |
|-----------|---------|-----------------|
| Architect | MISSING artifact | REQUEST_MAJOR_CHANGES |
| Security | MISSING artifact | CONDITIONAL_APPROVE |
| Designer | CONDITIONAL_APPROVE | CONDITIONAL_APPROVE |
| Performance | MISSING artifact | CONDITIONAL_APPROVE |
| Economy | MISSING artifact | REQUEST_MAJOR_CHANGES |
| API/DX | REQUEST_MAJOR_CHANGES | REQUEST_MAJOR_CHANGES |
| Determinism | CONDITIONAL_APPROVE | CONDITIONAL_APPROVE |

### 可用报告严重度分布（按 reviewer 自报/标题抽取）

| Reviewer | Verdict | Critical | High | Medium | Low |
|----------|---------|----------|------|--------|-----|
| rev-dsv4-architect | REQUEST_MAJOR_CHANGES | 3 | 3 | 4 | 3 |
| rev-dsv4-security | CONDITIONAL_APPROVE | 2 | 6 | 3 | 2 |
| rev-gpt-designer | CONDITIONAL_APPROVE | 0 | 2 | 3 | 0 |
| rev-dsv4-designer | CONDITIONAL_APPROVE | 1 | 3 | 3 | 2 |
| rev-dsv4-performance | CONDITIONAL_APPROVE | 3 | 3 | 2 | 0 |
| rev-dsv4-economy | REQUEST_MAJOR_CHANGES | 4 | 3 | 3 | 2 |
| rev-gpt-apidx | REQUEST_MAJOR_CHANGES | 1 | 3 | 3 | 0 |
| rev-dsv4-apidx | REQUEST_MAJOR_CHANGES | 4 | 4 | 4 | 0 |
| rev-gpt-determinism | CONDITIONAL_APPROVE | 0 | 2 | 3 | 0 |
| rev-dsv4-determinism | CONDITIONAL_APPROVE | 1 | 3 | 7 | 3 |
| **合计（10份）** | — | **19** | **32** | **35** | **12** |

注：部分报告正文中 severity 词出现次数与自报统计/标题统计略有差异；上表按 reviewer 摘要与标题结构归一化，不把章节标题重复计入。

### 共识强度评估

- **Very Strong**: B1 Host Function ABI、B2 Economy numeric drift、B3 Tick/Snapshot budget。均由 ≥3 方向、≥2 模型或多个独立 reviewer 发现。
- **Strong**: B4 MCP/API Registry drift、B5 Snapshot truncation strategy。均跨 API/DX、Designer、Security/Determinism。
- **Moderate but Critical**: B6 Auth/certificate/replay。主要由 Security DeepSeek 深入发现，API/DX 从 schema drift 侧面支持；由于内部矛盾是 Critical，仍列为 blocker。
- **Coverage Gap**: GPT Architect/Security/Performance/Economy artifact 缺失使共识矩阵不完整；但现有证据已经足以给出 REQUEST_MAJOR_CHANGES。

## R25 入场条件

1. B1-B6 已完成文档修正，并能提供 grep/CI/checklist evidence。
2. D1-D4 已由用户裁决并落实到 design/spec。
3. R25 reviewer fan-in 前必须校验 14/14 artifact 文件存在且非空；不得只依赖看板 done 状态。
4. R25 建议采用 Closure Verification：每个 reviewer 只验证 B1-B6 与 D1-D4 是否 CLOSED/GAP，不再开放式发现新问题。
