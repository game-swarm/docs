# R33 Speaker Verdict

## Overall Verdict

**REQUEST_MAJOR_CHANGES**

R33 的 10 份 Phase 1 独立评审全部读完，10/10 均给出 `REQUEST_MAJOR_CHANGES`。本轮不是局部措辞修正，而是多条“机器权威源/确定性合同/安全入口/经济参数”链路仍存在跨文档分叉。尤其 IDL→Registry→SDK/codegen、Host ABI、TickCommitRecord/replay-critical 边界、Auth 目标模型、经济权威表五条主线均被 ≥2 方向且 ≥2 模型共同命中，必须作为共识 Blocker 处理。

统计：

- APPROVE: 0
- CONDITIONAL_APPROVE: 0
- REQUEST_MAJOR_CHANGES: 10
- REJECT: 0

## Reviewer Summary

| Direction | DSV4 | GPT | Agreement |
|-----------|------|-----|-----------|
| Architect | REQUEST_MAJOR_CHANGES | REQUEST_MAJOR_CHANGES | agree |
| Security | REQUEST_MAJOR_CHANGES | REQUEST_MAJOR_CHANGES | agree |
| Design & Economy | REQUEST_MAJOR_CHANGES | REQUEST_MAJOR_CHANGES | agree |
| API/DX | REQUEST_MAJOR_CHANGES | REQUEST_MAJOR_CHANGES | agree |
| Determinism & Perf | REQUEST_MAJOR_CHANGES | REQUEST_MAJOR_CHANGES | agree |

Provenance：已读取全部 10 份报告，无缺失报告。

- `/data/swarm/docs/reviews/R33/rev-dsv4-architect.md`
- `/data/swarm/docs/reviews/R33/rev-dsv4-security.md`
- `/data/swarm/docs/reviews/R33/rev-dsv4-design-economy.md`
- `/data/swarm/docs/reviews/R33/rev-dsv4-apidx.md`
- `/data/swarm/docs/reviews/R33/rev-dsv4-determinism-perf.md`
- `/data/swarm/docs/reviews/R33/rev-gpt-architect.md`
- `/data/swarm/docs/reviews/R33/rev-gpt-security.md`
- `/data/swarm/docs/reviews/R33/rev-gpt-design-economy.md`
- `/data/swarm/docs/reviews/R33/rev-gpt-apidx.md`
- `/data/swarm/docs/reviews/R33/rev-gpt-determinism-perf.md`

## Consensus Blockers (B1..B9)

### B1 — IDL → Registry → SDK/codegen 单事实源链条失效

- 问题描述：`api-registry.md` 多处声明由 IDL 自动生成且冲突时 IDL 为机器权威，但当前 `game_api.idl.yaml`、`auth_api.idl.yaml`、`economy.idl.yaml`、`api-registry.md`、`mcp-tools.md`、`codegen.md`、`commands.md` 之间存在工具计数、分类、host function、CommandAction 字段、错误 envelope、auth shortcut schema 等多处漂移。
- 来源 reviewer：rev-dsv4-apidx B1/B2/B3/H3，rev-gpt-apidx B1/B2/B3/B4/B5/H1/H3/H6，rev-gpt-design-economy B3，rev-gpt-security B1，rev-gpt-architect H1，rev-gpt-determinism B3，rev-dsv4-security M2。
- 影响范围：MCP schema 暴露、TypeScript/Rust SDK codegen、IDE 自动补全、LLM agent few-shot 示例、CI diff gate、wire error handling、auth API 生成。
- 修复方向建议：以结构化 IDL YAML 为唯一机器源，重新生成 `api-registry.md`；所有派生文档中的工具计数、分类、CommandAction 示例、SwarmError envelope、auth shortcut、RejectionReason 必须由 IDL 或统一生成脚本校验。CI 不只做 markdown diff，而要解析并校验工具集合、per-category count、host function 集合、CommandAction 参数集合、error envelope schema、canonical RejectionReason 集合。

### B2 — Host Function / deterministic RNG ABI 不闭合：`host_get_random` 是否存在无法实现

- 问题描述：`api-registry.md` 注册 6 个 Host Functions，包含 `host_get_random`，并定义 seed、预算、输出上限；但 `game_api.idl.yaml`、`host-functions.md`、`design/interface.md`、`04-wasm-sandbox.md` 的 allowlist 仅有 5 个，不含 `host_get_random`。同时 sandbox 禁用 WASI random，tick protocol 又要求 WASM 使用 host 随机源。
- 来源 reviewer：rev-dsv4-apidx B1/M1，rev-gpt-apidx B2，rev-gpt-determinism B1，rev-gpt-architect B5，rev-dsv4-architect H3，rev-gpt-design-economy B3/CX2。
- 影响范围：WASM SDK import binding、sandbox allowlist、deterministic replay、fuel accounting、host ABI version、玩家代码随机能力。
- 修复方向建议：需要用户先裁决 `host_get_random` 是否为目标 ABI。若是，则回写 `game_api.idl.yaml`，同步 sandbox allowlist、host-functions.md、interface.md、预算/错误码/输出上限，并重新生成 Registry；若否，则从 Registry 与 RNG 文档删除并提供替代 deterministic random 设计。

### B3 — TickCommitRecord / TickTrace / ReplayArtifact 字段集合冲突，replay-critical 边界不唯一

- 问题描述：`engine.md` 的 TickInputEnvelope、`api-registry.md` 的 22 字段 TickTrace Envelope、`05-persistence-contract.md` 的 10 字段 TickCommitRecord、`01-tick-protocol.md` 的 terminal/wasm status 与 output truncation 字段并未形成单一字段映射。对象存储 RichTraceBlob 是否 replay-critical 也在 persistence 文档内部自相矛盾。
- 来源 reviewer：rev-gpt-architect B1/B2，rev-gpt-determinism B2，rev-gpt-security CX4，rev-dsv4-architect Strengths/相关 persistence 评论，rev-dsv4-determinism B2（T2 hash chain 与 persistence contract 脱节）。
- 影响范围：FDB schema、hash chain、replay verifier、anti-cheat 审计、terminal_state 分级、object store 降级、跨版本 fuel/host cost 验证。
- 修复方向建议：定义唯一 `TickCommitRecordVn` schema，列清 replay-critical 字段、rich/debug 字段、对象存储增强字段的边界；所有文档只引用该 schema。RichTraceBlob 缺失应最多导致 `audit_gap`/debug 降级，不应使 deterministic replay `unreplayable`，除非缺失的是 FDB replay-critical 字段或 keyframe/delta chain。

### B4 — Auth 目标模型与 `auth_api.idl.yaml` 机器权威分叉

- 问题描述：`design/auth.md` 的目标模型是应用层证书、用户持私钥、CSR challenge/submit/renew、certificate usage/audience、canonical request signature；但 `auth_api.idl.yaml` 仍呈现旧 bearer token、opaque refresh token、admin cert issue/rotate、TLS/mTLS/RSA/ECDSA/trust store 语义，且缺失多项 auth.md §10.1 工具。
- 来源 reviewer：rev-gpt-security B1/H5，rev-dsv4-security M2，rev-gpt-apidx H3，rev-dsv4-apidx L3，rev-gpt-design-economy B3（API/IDL 机器权威冲突）。
- 影响范围：Auth Service、Gateway、SDK auth client、MCP auth schema、证书信任边界、JWT/refresh token 信任根、CSR 注册流程。
- 修复方向建议：重写 `auth_api.idl.yaml` 为目标认证链的机器权威源，补齐 CSR/PoW challenge、CSR submit、renew/revoke/list、server trust、request signature、scope/audience、passkey/recovery/federation 等工具；删除或重命名旧 TLS/mTLS/internal CA 语义；重新生成 Registry 并让 `game_api` auth shortcuts 使用机器可读 `schema_source/alias_of`。

### B5 — 经济权威源冲突：核心成本、物流延迟、费用与结算顺序不可实施

- 问题描述：结构建造成本、RangedAttack cost、global deposit/withdraw delay、Allied daily cap、Upkeep vs StorageTax 顺序、Terminal 功能、PvE award tier、Road/Wall/Rampart 是否为结构等，在 `design/gameplay.md`、`07-world-rules.md`、`08-resource-ledger.md`、`economy.idl.yaml`、`economy-balance-sheet.md` 之间冲突。
- 来源 reviewer：rev-dsv4-design-economy B1/B2/H1/H2/H3/H4，rev-gpt-design-economy B2/H3/H4，rev-gpt-architect B6，rev-gpt-apidx H4，rev-dsv4-apidx M5。
- 影响范围：Resource Ledger、SDK tooltip、AI strategy、Balance Sheet、replay ledger、经济审计、玩家学习路径。
- 修复方向建议：裁决并写明权威分工：推荐 `08-resource-ledger.md` 为数学/执行顺序权威，`economy.idl.yaml` 为机器编码同一数值，design 文档只引用不重列。全量去重成本表、费用表、物流参数与结算顺序，所有派生表由同一 canonical table 生成或 lint。

### B6 — Canonical RejectionReason 与错误 envelope 未闭合，wire 错误不可规范化

- 问题描述：`MainActionQuotaExceeded`、`SourceEmpty`、`TileOccupied`、`AlreadyFullHealth`、`TargetFull`、`TickValidationFailed`、`output_truncated`、`ERR_CPU_SATURATED` 等错误名在 core/reference 文档中出现，但不在 Registry/YAML canonical RejectionReason 中，且 SwarmError envelope 在 IDL 与 Registry 中一版用 string `error.code`，一版用 JSON-RPC numeric code + `data.rejection_reason`。
- 来源 reviewer：rev-dsv4-apidx B3/H3/L1，rev-gpt-apidx B4/H6，rev-gpt-determinism B3，rev-gpt-architect H1/M4，rev-dsv4-architect M4，rev-dsv4-design-economy M3。
- 影响范围：SDK typed exception、wire enum、MCP tool error schema、TickCommitRecord rejection hash、safe hint ladder、debug_detail 机制。
- 修复方向建议：以一个 SwarmError envelope 为目标合同，并回写 IDL；所有正文错误名必须来自 canonical enum，旧码/细节进入 `debug_detail`。若确需新增 `MainActionQuotaExceeded` 等，先进入 IDL/Registry，再允许正文引用。

### B7 — Phase 2a/2b combat 与 HitPoints writer 合同冲突

- 问题描述：玩家 Attack/RangedAttack/Heal 是 Phase 2a inline 立即改 HP，还是 Phase 2b S11-S15 统一 reduce，并未全局统一。`engine.md`、`06-phase2b-system-manifest.md` 的 handled commands、R/W matrix、S15 HitPoints Unique Writer、S10 regen exception 互相冲突。
- 来源 reviewer：rev-gpt-architect B3，rev-dsv4-architect H2，rev-gpt-determinism M3，rev-dsv4-determinism CX2，rev-gpt-design-economy CX4。
- 影响范围：ECS 调度、parallel safety、先到先得语义、combat determinism、CI unique writer gate、death/heal/status 结算顺序。
- 修复方向建议：需要用户裁决 combat 结算模式。若选 inline，S11-S15 仅处理 Tower/DoT/auto effects 并从玩家 command handled list/RW 矩阵移除；若选 deferred，Phase 2a 只生成 intent，S11-S15 为 HP 唯一 reducer。无论哪种，CI writer set 必须机器可检验。

### B8 — Sandbox / security boundary 文档存在可实现性与高危语义冲突

- 问题描述：sandbox 网络隔离有“无网络命名空间”与“独立 net namespace 无接口”的冲突；Store reset 缺乏跨 tick 状态泄漏验证 checklist；WASM module size 5MB/64MB 分层不清；sensitive audit/object store/FDB 数据保护合同不足。
- 来源 reviewer：rev-gpt-security B3/H4/L2，rev-dsv4-security M1，rev-gpt-determinism Strength/CX5，rev-dsv4-determinism M1。
- 影响范围：WASM sandbox escape/SSRF、用户代码隔离、audit privacy、RichTrace/debug blob、部署 DoS、CVE 升级缓存失效。
- 修复方向建议：统一为独立 network namespace、默认无接口/无路由、seccomp 为第二层；加入 netns/route/connect 启动验证。补充 Store reset checklist、deployable wasm max vs object-store max 分层、audit parameter schema-aware redaction、object store encryption 与 KMS/retention/access-scope 合同。

### B9 — “设计即目标状态”原则仍被 MVP/P0/P1/Phase/Future/TBD 语义破坏

- 问题描述：modes、feedback-loop、snapshot-contract、engine、future/T2、future/T3 等文档仍保留 MVP/P0/P1/Phase/Tier/Future/TBD/候选方案/需冻结等语言。部分是纯措辞，部分实际影响 Arena、Allied Transfer、经济边界、T2/T3 replay 与 shard protocol 的目标合同。
- 来源 reviewer：rev-gpt-design-economy B4，rev-gpt-determinism H1/L1，rev-gpt-apidx M5，rev-gpt-architect M1/M3，rev-dsv4-determinism L2/H3，rev-dsv4-design-economy H5。
- 影响范围：设计治理、实现优先级、玩家预期、API active/RFC 划分、T2/T3 manifest/replay 稳定性。
- 修复方向建议：目标设计正文只保留确定状态。真正未进入核心设计的内容放 `RFC` / `Out-of-Scope` / `mod extension`；渐进玩法状态用 `Stage` / `Transition Window` 而非 Phase；需要用户裁决的候选项必须升为 D-item，不留在正文中。

## Direction-Specific Blockers / High (A-H, S-H, D-H, E-H)

### Architect-only / mostly Architect High

| ID | 来源 | 问题 | 处置建议 |
|----|------|------|----------|
| A-H1 | rev-dsv4-architect B1 | Leech/Fabricate 缺少 `02-command-validation.md` 独立校验矩阵 | 作为修复项直接闭合；与 D7 的 8 special attack canonical table 联动 |
| A-H2 | rev-dsv4-architect B2 | Overload `target_id` 在 EntityId / PlayerId 之间冲突 | 升为 D3 用户裁决 |
| A-H3 | rev-dsv4-architect B3 | ClaimController handler 同时出现在 S01/S02 | 直接修复：S01 移除 ClaimController，仅 S02 处理 Controller |
| A-H4 | rev-dsv4-architect H1 | TransferToGlobal/FromGlobal 缺少 Phase 2a handler 映射 | 与 B5 经济/ledger 单入口联动，直接修复 manifest |
| A-H5 | rev-gpt-architect B4 | Phase 2b “31 systems” vs S01-S29/S22a/S22b 编号冲突 | 直接修复为规范线性 system id 序列，并更新 manifest hash |
| A-H6 | rev-gpt-architect H4 | RuleMod 能力与直接 ECS 写入边界冲突 | 升为 D8 或作为 B9/Rhai ABI 修复项：禁止未登记 direct ECS writer |

### Security-only / mostly Security High

| ID | 来源 | 问题 | 处置建议 |
|----|------|------|----------|
| S-H1 | rev-dsv4-security B1 | Audience transport 标签 `agent-mcp` / `cli-rest` 三文档不一致 | 直接修复：agent MCP 统一为 `agent-mcp`，CLI REST 单独保留 |
| S-H2 | rev-dsv4-security B2 | Tutorial source 在 `09-command-source.md` 双重定义 | 直接修复：保留一处 canonical Tutorial source，补 budget |
| S-H3 | rev-gpt-security B2 | CSR admission/rate limit 表内冲突 | 直接修复：未认证端点表引用 §5.2 多层准入链 |
| S-H4 | rev-dsv4-security H1 | CRL fallback 枚举两处不一致 | 直接修复为统一枚举，并同步 IDL/Registry |
| S-H5 | rev-dsv4-security H2 | Refresh token rotation grace 缺 per-IP/UA 绑定 | 直接修复：grace token 绑定原始 IP hash + UA hash，不匹配 revoke |
| S-H6 | rev-dsv4-security H3 | Agent endpoint 未显式拒绝 JWT Bearer | 直接修复：Agent/CLI 端点只接受 certificate chain + signature |
| S-H7 | rev-gpt-security H1 | Auth TTL/session/lockout 参数冲突 | 纳入 B4 auth IDL 重构同步修复 |
| S-H8 | rev-gpt-security H2 | Admin source “无限制” vs Registry admin limits | 直接修复：Command Source 引用 API Registry limits + break-glass policy |
| S-H9 | rev-gpt-security H3 | Deploy signed payload 缺 certificate/audience/expiry binding | 直接修复：定义 `SWARM-DEPLOY-V1` canonical payload |
| S-H10 | rev-gpt-security H6 | non-competitive full visibility 缺 world security label | 升为 D9 或直接修复：新增 `world.security_class` 与 API posture warning |

### Design & Economy-only / mostly Gameplay High

| ID | 来源 | 问题 | 处置建议 |
|----|------|------|----------|
| D-H1 | rev-gpt-design-economy B1 | Standard 经济曲线全阶段净亏损，没有自维持区间 | 升为 D4 用户裁决，且需 playtest-gated/Balance Sheet 重算 |
| D-H2 | rev-gpt-design-economy B5 | Diplomacy allied direct transfer 绕过 Restricted Allied Transfer | 直接修复：外交文档引用 Restricted Allied Transfer，不允许免延迟直转 |
| D-H3 | rev-gpt-design-economy H1 | Feedback Loop 承诺事件推送但 API 缺订阅/schema | 升为 D6 用户裁决事件通道 |
| D-H4 | rev-gpt-design-economy H2 | Arena “无天梯/无赛季” vs active leaderboard/tournament API | 升为 D5 用户裁决 |
| D-H5 | rev-gpt-design-economy H4 | PvE faucet 掉落表与 Ledger award tier 不闭合 | 直接修复：建立 NPC/entity_tier → PvEAward budget 映射 |
| D-H6 | rev-gpt-design-economy H5 | Novice/Vanilla/Standard 命名混用 | 直接修复 taxonomy：Ruleset vs Difficulty/Profile |
| D-H7 | rev-dsv4-design-economy H3 | Terminal 功能描述“身份同步” vs “市场交易接口” | 升为 D10 或直接按目标功能裁决后统一 |

### API/DX-only / mostly Interface High

| ID | 来源 | 问题 | 处置建议 |
|----|------|------|----------|
| E-H1 | rev-gpt-apidx H2 | `global_storage` / `economy_operation` category 命名不一致 | 直接修复：选定 canonical wire category，推荐 `economy_operation` |
| E-H2 | rev-gpt-apidx H4 | Type registry 单位/命名不稳定，影响 TS branded types | 直接修复：同名类型 scale/unit/range/rounding 必须完全一致 |
| E-H3 | rev-gpt-apidx H5 | Snapshot/MCP output schema `omitted_count` vs `omitted_categories` 不一致 | 与 D11 snapshot 粒度/输出 schema 裁决联动 |
| E-H4 | rev-gpt-apidx M4 | codegen 命令 `hermes codegen` 与项目名混淆 | 直接修复为实际脚本或 `swarm codegen` |
| E-H5 | rev-dsv4-apidx L2 | commands.md Recycle 校验保留旧 Spawn proximity | 直接修复为 self-action no spawn proximity |

### Determinism & Performance-only / mostly Performance High

| ID | 来源 | 问题 | 处置建议 |
|----|------|------|----------|
| P-H1 | rev-dsv4-determinism B1 | EXECUTE 独立 500ms hard cap vs unified budget 表冲突 | 直接修复：以统一预算表为权威，明确 watchdog/soft/hard deadline 分层 |
| P-H2 | rev-dsv4-determinism B2 | T2 incremental snapshot 缺 hash chain 验证设计 | 直接修复：modification_set self_hash/prev_hash + keyframe chain_head_hash |
| P-H3 | rev-gpt-determinism H2 / rev-dsv4-determinism H3 | T3 cross-shard combat tick sync/intent log 未定义 | 升为 D12 或标为 Out-of-Scope RFC，不留在目标规范正文 |
| P-H4 | rev-gpt-determinism H3 / rev-dsv4-determinism H2 | 1000-player hard cap 与 benchmark-gated 状态冲突 | 直接修复：1000 仅 benchmark-gated，不称 hard guarantee |
| P-H5 | rev-dsv4-determinism H1 | Admission hysteresis 非对称可能永久欠准入 | 直接修复或 benchmark-gated：恢复路径对称化 + admin override |
| P-H6 | rev-dsv4-determinism M1 | Wasmtime upgrade 后 module cache 全量失效风险 | 直接修复：pre-warm/dual engine/cutover 策略 |

## CrossCheck 发现

无 Phase 2 补充报告；本节仅综合 Phase 1 CrossCheck 中可闭合的跨方向补漏。

| CX | 来源 | 内容 | 处置 |
|----|------|------|------|
| CX1 | 多份 API/Security/Determinism | `host_get_random` 牵涉 RNG domain separation、fuel、sandbox allowlist、SDK 名称 | 纳入 B2 + D1 |
| CX2 | Architect/Security/Determinism | TickCommitRecord/RichTraceBlob/object store 降级语义影响 anti-cheat 与 replay | 纳入 B3 |
| CX3 | API/Security | Auth IDL 与 auth.md 分叉影响 Gateway/Auth Service/codegen | 纳入 B4 |
| CX4 | Design/API/Security | Allied Transfer 涉及 fee/delay/cap/intercept/RNG/visibility/audit | 纳入 B5 + D7/D11 相关修复 |
| CX5 | Determinism/Security | Snapshot truncation critical entity 集合可能被敌方堆实体造成信息 DoS | 升为 D11 |
| CX6 | Architecture/API/Determinism | Rhai RuleMod `actions.*` 可能绕过 validation 或影响 manifest hash | 纳入 A-H6，建议修复为 manifest-registered action buffer |
| CX7 | Security/Performance | CSR admission 多节点 rate limiter/queue/semaphore 容量参数需一致 | 纳入 S-H3，直接修复为权威 admission 链 |
| CX8 | Design Governance | `PLAYTEST-GATED.md` 是否登记经济曲线/storage tax/special attack 等待验证项需确认 | 修复时必须同步，不在 Speaker 阶段读取额外目标文档 |

## Medium/Low 汇总

| Severity | Direction | 数量级 | 处置建议 |
|----------|-----------|--------|----------|
| Medium | Architect | 约 5 | 多为引用、术语、envelope 分层细节；与 B3/B9 修复一起直接闭合 |
| Low | Architect | 约 3-4 | Markdown/link/示例/路径清理，deferred 或批量文档 lint |
| Medium | Security | 约 4-5 | canonical body、WS schema、CVE owner、HTTP encrypted payload 等；S-H/B4 修复后同步闭合 |
| Low | Security | 约 2-4 | 链接、脱敏格式、模块大小分层、oracle trade-off 注释；直接闭合 |
| Medium | Design & Economy | 约 4 | Fabricate cost、Balance Sheet break-even、visibility 默认、objective reward 等；与 B5/D4/D7 联动 |
| Low | Design & Economy | 约 2-3 | 重复标题、旧修复标记、Arena storage tax note；直接闭合 |
| Medium | API/DX | 约 5 | sdk_fetch examples、MCP vs host tool 边界、Rhai schema、codegen command、MVP/Future 术语；多数直接闭合 |
| Low | API/DX | 约 3-4 | 相对链接、section mapping、api_version/changelog；直接闭合 |
| Medium | Determinism & Perf | 约 4 | pathfinding budget vs fuel、cache line、snapshot float debug、引用章节漂移；直接闭合 |
| Low | Determinism & Perf | 约 3 | Parallel Set C 命名、T2 推荐措辞、FDB budget 对齐；直接闭合或随 B9 修复 |

处置原则：

- 与 B1-B9 同源的 Medium/Low 不单独开 D-item，随对应 Blocker 修复时闭合。
- 纯 wording/link/table/count 低风险项直接批量修复。
- 任何影响目标状态选择、玩法承诺、wire ABI、结算模式、可见性边界的项升为 D-item。

## D-Items（需要用户裁决的设计决策）

### D1: Host RNG ABI — `host_get_random` 是否进入核心 Host Function 集合

- 背景：多份报告指出 Registry 有 `host_get_random`，IDL/sandbox/host-functions/interface 无；WASI random 被禁用，WASM 需要 deterministic random source。
- 方案A：纳入核心 ABI — 在 `game_api.idl.yaml`、sandbox allowlist、host-functions.md、interface.md、Registry/codegen 中统一添加 `host_get_random(sequence, out_ptr, out_len)`，定义 seed、fuel、输出上限、错误码、host ABI version。— 推荐
- 方案B：不纳入核心 ABI — 从 Registry/tick protocol 删除 `host_get_random`/`swarm_get_random` 相关承诺，玩家 WASM 不获得随机字节或改由其他 deterministic API 提供。— 不推荐
- Speaker 推荐：A。理由：当前设计已经依赖玩家可用 deterministic random；删除会破坏玩法/SDK 预期。关键是把它纳入机器权威，而不是保留半存在状态。

### D2: Combat HP 结算模式 — Phase 2a inline 还是 Phase 2b deferred reducer

- 背景：Attack/RangedAttack/Heal 与 Tower/DoT/Status 的 HP 写入路径在 engine 与 manifest 中冲突，影响 HitPoints writer contract。
- 方案A：Phase 2a inline 玩家战斗 — 玩家 Attack/RangedAttack/Heal 在 Phase 2a 立即应用；S11-S15 只处理非玩家自动战斗、DoT、Tower、status buffer；S01/S10/S15 writer set 明确区分 phase/语义。— 可选
- 方案B：Phase 2b deferred reducer — Phase 2a 只校验并生成 PendingDamage/PendingHeal intent；S11-S15 统一排序/归并/应用 HP，S15 成为主要 HP reducer。— 推荐
- Speaker 推荐：B。理由：更符合 ECS manifest、unique writer、parallel safety、combat audit；但会改变“先到先得即时生效”语义，需要明确同 tick 后续命令读取的是 pre-combat 还是 pending-combat 状态。

### D3: Overload `target_id` 目标类型 — PlayerId 还是 EntityId

- 背景：Overload 是 player-level fuel budget attack，但 Registry/YAML 目前是 EntityId，部分 spec/validation 以 PlayerId 解释。
- 方案A：改为 `PlayerId` / `OverloadTarget` — Overload 明确攻击玩家级 fuel budget，定义可见性检查为“至少一个可见实体/交互关系证明目标玩家存在”，避免 entity schema 伪装。— 推荐
- 方案B：保留 `EntityId` — Overload 改为 entity-level pressure，再由 entity owner 映射到 player fuel budget；所有 validation 与 UX 统一按实体目标。— 不推荐
- Speaker 推荐：A。理由：设计语义本质是 player-level budget pressure；继续用 EntityId 会让 schema 类型安全掩盖真实目标，并造成 cooldown/keying 语义不清。需由 Security 检查 oracle 风险。

### D4: Standard 经济曲线 — 目标自维持区间还是显式 deflationary

- 背景：Balance Sheet 当前 2-50 房全为负流量，但文档宣称 Full economy self-sustaining；这是玩法目标层选择，不只是数字修正。
- 方案A：建立中期自维持区间 — 2-5 房在良好代码/RCL/PvE/适度扩张下可小幅正流量，20+ 明显递减，50 接近不可持续；重算参数并登记 playtest-gated 项。— 推荐
- 方案B：Standard 明确为长期 deflationary — 所有扩张均净亏，玩家必须依赖 PvE/联盟/周期性奖励等外部 faucet；删除 self-sustaining 承诺。— 不推荐
- Speaker 推荐：A。理由：用户既往偏好是设计文档呈现目标状态，Standard 应有可学习、可优化、可达的中期平台；全阶段亏损会削弱玩家动机并使反雪球变成反成长。

### D5: Arena 目标状态 — 房间制测试场还是带 leaderboard/tournament 的竞技体系

- 背景：modes/feedback-loop 说无天梯/无赛季/Tournament 非核心，但 API active capability 暴露 leaderboard/tournament/match_result。
- 方案A：Arena 核心包含 leaderboard/tournament — 删除“无天梯/无赛季/P1+”语义，补赛季范围、排名公平性、奖励/反作弊、commit-reveal 审计。— 可选
- 方案B：Arena 核心为轻量房间制测试场 — 将 leaderboard/tournament 移出 active API，标为 RFC/admin-only/out-of-scope，不计入 active capability。— 推荐
- Speaker 推荐：B。理由：与“设计即目标状态”一致，若竞技体系未完整定义，不应以 active API 暴露承诺。可保留 room match_result，不承诺赛季/天梯。

### D6: Deploy/event feedback 通道 — WebSocket subscription、MCP subscription 还是 polling

- 背景：Feedback Loop 承诺 `deploy_accepted`、`first_tick_executed` 主动推送，但 API/IDL 缺事件 schema 和订阅能力。
- 方案A：定义主动事件通道 — 增加 WebSocket channel 或 MCP subscription schema，覆盖 deploy_accepted、first_tick_executed、economy_warning、tick_integrity 等事件。— 推荐
- 方案B：改为 polling-only — 删除主动推送承诺，Golden Path 使用 `swarm_get_deploy_status` / `swarm_get_events` 拉取。— 不推荐
- Speaker 推荐：A。理由：AI/human 10 分钟闭环依赖即时反馈；主动事件通道是目标体验的一部分，应机器可读化，而不是降级为轮询。

### D7: 8 个特殊攻击 canonical table — 独立核心表还是散落在 validation/world-rules/gameplay

- 背景：Leech/Fabricate 缺 validation matrix，Fabricate cost、Leech resistance、Overload target、RangedAttack/Fabricate 参数均有漂移。
- 方案A：建立单一 canonical special attack table — 8 个特殊攻击统一列 body part、damage_type/resistance、cost、cooldown、range、channel、counterplay、validation schema，并由 design/spec/IDL 引用。— 推荐
- 方案B：保留分散表，逐处修正当前冲突。— 不推荐
- Speaker 推荐：A。理由：用户已裁决 8 special attack 全部为目标设计；分散表会持续漂移。

### D8: RuleMod 能力边界 — 是否允许直接 ECS writer

- 背景：world-rules 一方面说 RuleMod 通过 action buffer 不能绕过 validation，一方面又暗示可修改 ECS resource/component。
- 方案A：禁止直接 ECS writer — RuleMod 只能产生声明式 world param/ledger action/event hook/action buffer，所有写入进入已登记系统和 manifest hash。— 推荐
- 方案B：允许受 capability gate 的 direct ECS writer — 但每个 writer 必须进入 system manifest/hash、R/W matrix、TickTrace audit，并通过 CI unique writer 检查。— 不推荐
- Speaker 推荐：A。理由：核心机制 = 最终设计，扩展复杂度留给 mod，但 mod 不能创建第二条不可审计状态修改路径。A 更安全且易 replay。

### D9: World visibility/security class — 是否引入强制 `world.security_class`

- 背景：Visibility 允许 tutorial/coop/sandbox 关闭 fog_of_war，MCP security 又承诺 AI 与 Web UI 等量信息；缺模式级安全标签会导致 competitive world 配错。
- 方案A：引入 `world.security_class = competitive | cooperative | tutorial | sandbox` — competitive 强制 fog_of_war，非 competitive 全图可见必须在 API response 中显式 posture warning。— 推荐
- 方案B：仅保留当前 visibility config，不增加 security class。— 不推荐
- Speaker 推荐：A。理由：这不是限制玩法，而是防配置误用与玩家预期错配；对竞技公平和 AI/MCP 权限心智有价值。

### D10: Terminal 目标功能 — Identity/logistics node 还是 market interface

- 背景：gameplay 将 Terminal 描述为跨世界身份同步与日志交换节点，world-rules 描述为市场交易接口，economy-balance-sheet 又说 market trading 是 RFC 占位。
- 方案A：Terminal = identity/logistics/log exchange node — 当前核心不承诺市场交易，world-rules 同步改写。— 推荐
- 方案B：Terminal = market trading interface — gameplay 改写，补市场交易 scope、经济/安全/反滥用规则。— 不推荐
- Speaker 推荐：A。理由：市场交易尚未形成完整经济/安全设计，作为核心结构功能会扩大未闭合面；identity/logistics 更贴合当前文档主线。

### D11: Snapshot 输出粒度与 critical entity 截断边界

- 背景：Snapshot Contract 中 per-drone/per-player 粒度、`omitted_count`/`omitted_categories`、critical entity 不可截断在极端场景下占满 256KB 等问题并存。
- 方案A：统一为 per-player snapshot + actor context，并设置 critical entity size reserve — MCP/WASM 输出 schema 使用 `omitted_categories`，关键实体若超过阈值按 deterministic priority 截断/降级 tick。— 推荐
- 方案B：保留 per-drone snapshot，每个 drone 独立 perception cap，critical entity 永不截断。— 不推荐
- Speaker 推荐：A。理由：per-player 更符合 engine/tick protocol 的构建模型，且需要防止敌方通过堆实体让对手 snapshot 退化为信息 DoS。

### D12: T2/T3 future 文档状态 — 目标规范还是 RFC/out-of-scope

- 背景：T2/T3 包含候选/待定/需冻结，且涉及 keyframe/hash chain、shard assignment、cross-shard combat tick sync、intent log 等 replay-critical 决策。
- 方案A：改写为目标状态规范 — 当前就裁决唯一 keyframe/hash/shard/cross-shard intent 语义，纳入 manifest/replay 合同。— 不推荐（除非用户现在要推进 T2/T3）
- 方案B：降级为 RFC/out-of-scope future notes — 不作为当前目标设计评审阻塞项；正文核心规范不引用未裁决候选语义。— 推荐
- Speaker 推荐：B。理由：当前 R33 主阻塞已集中在核心 API/Auth/Economy/Replay；T2/T3 若未准备裁决，应从目标规范中隔离，避免污染“设计即目标状态”。

## Final Gate

R33 不可进入 approve/conditional。建议下一轮修复优先级：

1. 先闭合 B1/B2/B4/B6：IDL/Registry/Auth/Host ABI/Error envelope 机器权威链。
2. 并行闭合 B3/B7：TickCommitRecord replay-critical schema 与 combat writer contract。
3. 再闭合 B5：经济权威表与 Standard curve D4 裁决。
4. 最后批量清理 B8/B9 与 Medium/Low，避免 Phase/MVP/Future/TBD 语言继续污染目标设计。
