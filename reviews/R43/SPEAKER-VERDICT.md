# R43 Speaker 裁决

## 裁决概要

Overall Verdict: **REQUEST_MAJOR_CHANGES**

R43 的 9 份 Phase 1 clean-slate 评审均已实际读取并纳入综合：3 个模型（GPT / DeepSeek V4 / GLM）× 3 个方向（Architecture / Design & Economy / Cross-Cutting）。本轮文档的总体架构方向被广泛认可：COLLECT/EXECUTE 两层模型、per-shard single writer、Shadow Write + Atomic Publish、Resource Ledger 单入口、fixed-point determinism、MCP 不直接执行游戏动作等核心原则均获得多方正面评价。

但评审共识显示：reference/IDL/Registry/codegen、Auth 控制面、Deploy 状态机、目标状态文档治理、经济数学闭环等关键合同仍存在硬冲突。它们会直接影响 SDK/codegen、Gateway/Auth 实现、replay/determinism、经济调参基准和玩家可理解性，因此不能以 CONDITIONAL_APPROVE 进入冻结。

Verdict tally:

| Reviewer | Direction | Model | Verdict |
|---|---:|---:|---|
| rev-gpt-architect | Architecture | GPT | REQUEST_MAJOR_CHANGES |
| rev-gpt-design-economy | Design & Economy | GPT | REQUEST_MAJOR_CHANGES |
| rev-gpt-cross-cutting | Cross-Cutting | GPT | REQUEST_MAJOR_CHANGES |
| rev-dsv4-architect | Architecture | DeepSeek V4 | REQUEST_MAJOR_CHANGES |
| rev-dsv4-design-economy | Design & Economy | DeepSeek V4 | REQUEST_MAJOR_CHANGES |
| rev-dsv4-cross-cutting | Cross-Cutting | DeepSeek V4 | REQUEST_MAJOR_CHANGES |
| rev-glm-architect | Architecture | GLM | CONDITIONAL_APPROVE |
| rev-glm-design-economy | Design & Economy | GLM | CONDITIONAL_APPROVE |
| rev-glm-cross-cutting | Cross-Cutting | GLM | REQUEST_MAJOR_CHANGES |

统计：APPROVE 0 / CONDITIONAL_APPROVE 2 / REQUEST_MAJOR_CHANGES 7 / REJECT 0。

Provenance: 9/9 reports present. 无缺失 reviewer 报告。

## Consensus Summary — 三方共识点

### 共识正向结论

1. **两层计算模型成立**：Architecture 与 Cross-Cutting 多个 reviewer 均确认 WASM/COLLECT 与 Engine/EXECUTE 分层清晰，水平扩展只放在 untrusted WASM execution 层，权威世界模拟保持 deterministic single writer。
2. **持久化原子性模型方向正确**：Shadow Write + GlobalTickCommit/Atomic Publish 被 GPT、DSV4、GLM 架构向共同认为是关键亮点，能消除 per-room durable 但 global abort 的 TOCTOU 窗口。
3. **Resource Ledger 单入口方向正确**：Design & Economy 三个模型均肯定资源流分类、Transfer Gateway、定点费率、确定性执行顺序是正确的经济底座。
4. **fixed-point determinism 是稳定基石**：Cross-Cutting 与 Architecture 多方均肯定 BasisPoints / ResourceRate_i64 / milli_distance 等类型注册表清除了 f64 replay 风险。
5. **MCP 与 WASM 权限边界正确**：MCP 作为学习、调试、部署入口而非游戏动作入口被多方认可，符合 AI agent 与人类玩家同权原则。

### 共识负向结论

1. **IDL ↔ Registry ↔ codegen 单事实源已经系统性漂移**，不是单点 typo。
2. **Auth 设计与 auth_api.idl.yaml / Registry 存在旧模型残留**，尤其 Intermediate CA、admin certificate profile、passkey/device/federation surface、TTL、Swarm-Cert-Id 等。
3. **Deploy flow 仍在同步 deploy_mutation 与 async object-store deploy 两套架构之间分裂**。
4. **目标状态文档仍残留 future/deferred/Phase/changelog/date/Rxx 等历史或延期语言**，违反仓库文档治理原则。
5. **经济文档需要数学闭环与可审计计算**：数值冲突、storage tax 计算错误、anti-snowball proof 仅为定性断言等问题集中出现。

## 共识 Blocker（B1..B5）

### B1 — IDL / API Registry / codegen 单事实源合同断裂

- 问题描述：`api-registry.md`、`game_api.idl.yaml`、`auth_api.idl.yaml`、`codegen.md` 同时承担 schema 权威或生成产物角色，但内容互相冲突。冲突覆盖版本号、host function 数量、RejectionReason 总数和归属、JSON-RPC error envelope、deploy schema、per-player drone cap、host_get_random ABI 与 fuel、WebSocket signature payload、visibility_filter、replay_class 等。
- 来源 reviewer：rev-gpt-cross-cutting F2/F3/F4；rev-glm-cross-cutting C1/C2/C3/C4/H1/M4/M5/M6/M7/M8/M9；rev-dsv4-cross-cutting C2/H1/M3；rev-gpt-architect A-H2/A-H3；rev-gpt-design-economy CX1；rev-dsv4-architect CX1。
- 共识条件：≥2 方向（Cross-Cutting、Architecture、Design & Economy crosscheck）+ ≥2 模型（GPT、GLM、DSV4）。
- 影响范围：SDK generation、MCP schema、Gateway routing、WASM ABI、JSON-RPC error handling、replay determinism、CI `--check`。
- 修复方向建议：先裁定单事实源层级。Speaker 推荐方向见 D1：`*.idl.yaml` 作为唯一机器源，Registry 作为生成的人类可读 canonical publication；所有手写 Registry 冲突必须反向修回 IDL 后重新生成。随后建立 CI gate：IDL → Registry 生成 diff 必须 clean。

### B2 — Auth 控制面仍混用单层 CA / Intermediate CA / admin profile / token-era 残留

- 问题描述：设计层声明应用层证书、单层 Server CA、两类证书（ClientAuthCertificate / CodeSigningCertificate），但 auth IDL 与 Registry 仍出现 Intermediate CA、root/intermediate fingerprint、admin 证书 profile、passkey/device/federation active tools、RefreshTokenInvalid/TokenRevoked 等 token-era 残留；ClientAuth TTL 也存在 24h vs 15min–180d 的冲突。
- 来源 reviewer：rev-gpt-cross-cutting F1；rev-dsv4-cross-cutting C1/C2/C4/H2/H3；rev-glm-cross-cutting H2/H3/M2/M3；rev-gpt-architect A-H5。
- 共识条件：≥2 方向（Cross-Cutting、Architecture）+ ≥2 模型（GPT、DSV4、GLM）。
- 影响范围：Gateway certificate verifier、Auth API codegen、MCP auth tools、CA key custody、安全审计、客户端请求签名格式。
- 修复方向建议：以最终 Auth 目标模型统一所有机器源和 reference 文档。必须明确：Server CA 单层术语、CA signer/key custody、admin 是否仅为 scope flag、恢复方式是否仅 email optional、device/federation/passkey 是否 active、TTL 默认值与上限、Swarm-Cert-Id 来源。

### B3 — Deploy 状态机在同步 redb deploy_mutation 与 async object-store activation 之间分裂

- 问题描述：部分文档要求 `swarm_deploy` 同步提交 deploy_payload / code_signature / certificate_id / version_counter，并由 redb manifest + compiled artifact 决定 tick boundary activation；部分 IDL/flow 仍描述 `wasm_bytes`、`object_store_key`、async object-store upload，甚至把 blob upload complete 作为 activation 条件。
- 来源 reviewer：rev-gpt-architect A-H3；rev-gpt-cross-cutting F3；rev-glm-cross-cutting C4/L3；rev-dsv4-architect CX4；rev-glm-architect 3.5 亮点同时确认同步 deploy 状态机为合理方向。
- 共识条件：≥2 方向（Architecture、Cross-Cutting）+ ≥2 模型（GPT、GLM、DSV4）。
- 影响范围：Deploy security chain、CodeSigningCertificate verification、replay ordering、redb_version_counter、object-store audit gap、玩家部署 UX。
- 修复方向建议：裁定一个 deploy authority。Speaker 推荐见 D4：redb manifest + compiled artifact 是 activation 必要条件；raw WASM blob/object store 属于审计与归档路径，不阻塞 activation。IDL 必须移除以 `wasm_bytes + object_store_key` 为核心的 deploy API。

### B4 — 目标状态文档治理违规导致“最终设计”与“延期/历史记录”混杂

- 问题描述：多个 design/spec/reference 文件仍保留“远期方向”、future、deferred、Phase、playtest 阶段、日期化 changelog、Rxx 修复来源、旧/当前设计等历史或延期表述。R43 评审中这些词不只是风格问题：它们与“设计即目标状态”原则冲突，并且会让已废弃模型（bearer token、Intermediate CA、async deploy、RFC tools）重新污染实现判断。
- 来源 reviewer：rev-dsv4-architect A1；rev-gpt-architect A-L1；rev-gpt-cross-cutting F6；rev-gpt-design-economy D-ECO-7/CX2；rev-glm-design-economy 2.8；rev-glm-cross-cutting L2。
- 共识条件：≥3 方向（Architecture、Design & Economy、Cross-Cutting）+ ≥3 模型（GPT、DSV4、GLM）。
- 影响范围：全部 design/spec/reference 文档治理；API Registry/IDL changelog；PLAYTEST-GATED；目标状态评审语境。
- 修复方向建议：从目标规格正文移除历史追踪与延期语言。需要实证校准的内容改写为 Empirical Calibration Requirements；不属于目标 active surface 的 RFC/tool/market/leaderboard 内容移出 active 文档或明确作为独立 RFC，不得以 future/deferred/计划中留在目标状态正文。

### B5 — 经济模型目标曲线与数值闭环不足以支撑冻结

- 问题描述：Design & Economy 三个模型均认为经济底座方向正确，但发现大量需要修复的数学与权威源问题：Resource Ledger 与 Balance Sheet 的自维持曲线冲突；BuildCost 数值冲突；storage tax 计算错误和 tier discontinuity；anti-snowball proof 仅为定性断言；active aging、recycle、intercept、PvE budget 等关键策略子博弈缺少均衡说明；storage_capacity/per-drone upkeep/MIN_LIFESPAN 等权威值缺失。
- 来源 reviewer：rev-gpt-design-economy D-ECO-1..D-ECO-6；rev-dsv4-design-economy C1..C6/H1..H5；rev-glm-design-economy 2.1..2.7。
- 共识条件：同一方向内 3 模型强共识；并通过 CrossCheck 影响 Architecture / Interface / Engine。严格按“≥2 方向”规则，B5 是“方向强共识 Blocker”，不是跨方向 schema blocker；但其影响足以进入 P0/P1 修复队列。
- 影响范围：玩家 opening path、anti-snowball 可信度、storage/global-local 物流策略、PvE faucet、balance sheet 可审计性、server operator 参数调校。
- 修复方向建议：先修正权威数值与算术错误，再为核心经济曲线补“公式性质 + 参数目标 + playtest 校准项”的三层表达。不要把缺少 rationale 的设计留给 playtest 发明；playtest 只校准参数，不裁定机制理由。

## CrossCheck Synthesis — 跨方向 CrossCheck 汇总

| CX | 去重主题 | 源方向 → 目标方向 | 涉及 reviewer | 严重度 | Speaker 处置 |
|---|---|---|---|---|---|
| CX-1 | IDL/Registry/codegen drift：version、RejectionReason、host functions、deploy、error envelope | Cross-Cutting/Design → API/codegen/Architecture | gpt-cross, glm-cross, dsv4-cross, gpt-design | Critical | 并入 B1，P0 |
| CX-2 | Auth 单层 CA vs Intermediate CA / trust fields / admin profile / passkey surface | Cross-Cutting/Architecture → Security/Auth | gpt-cross, dsv4-cross, glm-cross, gpt-architect | Critical | 并入 B2，P0 |
| CX-3 | Deploy activation 与 object-store blob upload 关系 | Architecture/Cross-Cutting → Engine/Persistence | gpt-architect, gpt-cross, dsv4-architect, glm-cross | Critical | 并入 B3，P0/D4 |
| CX-4 | Recycle proximity：self-action no proximity vs Spawn 1 格 | Cross-Cutting → Gameplay/Engine | gpt-cross, dsv4-cross, glm-cross | High | P0/D6；单方向多模型强共识 |
| CX-5 | Transport/audience/capability labels 不一致 | Architecture/Cross-Cutting → Security/Interface | gpt-architect, dsv4-architect, dsv4-cross | High | P0；纳入 B1 的 auth/transport 子项 |
| CX-6 | Host Function vs MCP Tool namespace 混淆 | Cross-Cutting/Architecture → API/SDK | gpt-cross, dsv4-architect, glm-cross | High | P0；纳入 B1 |
| CX-7 | Mod 静态编译 vs 下一 tick upgrade/disable | Architecture/Cross-Cutting → Engine/Mod | gpt-architect, gpt-cross | High | P1/D5；未达多模型，但架构风险明确 |
| CX-8 | TickInputEnvelope/terminal_state/wasm_status 字段对齐 | Architecture → API/Engine | dsv4-architect, dsv4-cross | High | P1；需字段级对齐 |
| CX-9 | Economy balance sheet storage tax / capacity / per-drone upkeep / MIN_LIFESPAN | Design & Economy → Engine/Economy | gpt-design, dsv4-design, glm-design | High | 并入 B5，P0/P1 |
| CX-10 | Drone messages in gameplay but absent from tick() IDL; possible Resource Ledger bypass | Design & Economy → Interface/Engine/Security | glm-design | Medium/High | P1；Direction High |
| CX-11 | PvE World/Arena/Boss/faucet/ranking boundary | Design & Economy → Gameplay/API/Economy | gpt-design, dsv4-design | High | P1/D8 |
| CX-12 | JSON integer-only boundary vs JCS allowing floats | Architecture/Cross-Cutting → Determinism/API | glm-architect, gpt-design CX3 | Medium | P1；add schema rejection rule |
| CX-13 | Visibility rules for market/leaderboard/RFC-gated inactive tools | Architecture/Cross-Cutting → Interface/Security | glm-architect, glm-cross | Medium | P2；also covered by B4 governance |
| CX-14 | Allied/global transfer fee taxonomy and interception visibility/TOCTOU | Design & Economy/Cross-Cutting → Security/Engine | gpt-design, glm-cross, dsv4-design | Medium/High | P1；clarify fee layers and visibility |
| CX-15 | Documentation historical/future/deferred/changelog residue | All directions → Docs Governance | gpt-architect, gpt-cross, gpt-design, dsv4-architect, glm-design, glm-cross | High | 并入 B4，P0/P1 |

Phase 2 补漏发现：无 Phase 2 报告；本裁决仅综合 Phase 1 的 9 份 reviewer 报告和其中 CrossCheck 条目。

## Conflict Resolution — 冲突点裁决

### CR1 — 7 个 REQUEST_MAJOR_CHANGES vs 2 个 CONDITIONAL_APPROVE

- Disagreement：GLM Architecture 与 GLM Design & Economy 给出 CONDITIONAL_APPROVE；其余 7 份报告给出 REQUEST_MAJOR_CHANGES。
- Speaker 裁决：**REQUEST_MAJOR_CHANGES**。
- 理由：GLM 的两个 CONDITIONAL_APPROVE 仍列出 High/Medium 硬问题；同时 Cross-Cutting 三模型都发现 machine-readable contract 级冲突。只要 IDL/Registry/Auth/Deploy 不能生成一致 SDK 和实现，整体不能条件通过。

### CR2 — Registry 是 canonical authority 还是 IDL 是机器源？

- Disagreement：部分文档把 Registry 称为 canonical schema authority，codegen.md 又称 IDL 是唯一机器源、Registry 由 codegen 生成。
- Speaker 裁决：需用户在 D1 确认；Speaker 推荐 **IDL as machine source, Registry as generated canonical publication**。
- 理由：schema、ABI、SDK 生成必须有机器可验证源；人工维护 Registry 作为唯一权威会继续产生漂移。

### CR3 — Auth 是否只保留单层 Server CA + 两类证书？

- Disagreement：design/auth 倾向单层 CA + 两证书；auth IDL/Registry 残留 Intermediate CA、admin profile、passkey/device/federation/token-era code。
- Speaker 裁决：需用户在 D2/D7 确认；Speaker 推荐 **以单层 Server CA + 两类证书 + admin scope flag 为目标**。
- 理由：这是 R43 多数 reviewer 认为更一致的方向，且与项目“应用层证书”设计哲学匹配。

### CR4 — Deploy activation 是否依赖 raw WASM blob upload complete？

- Disagreement：tick-protocol/IDL 部分描述 blob upload complete 后才激活；persistence-contract/Registry 描述 redb manifest + compiled artifact 可激活，blob 缺失仅 audit gap。
- Speaker 裁决：需用户在 D4 确认；Speaker 推荐 **不依赖 blob upload complete**。
- 理由：将 object store I/O 放入 activation critical path 会破坏 replay-critical subset 与持久化分层；compiled artifact + manifest 才是执行必要条件。

### CR5 — Recycle 是否需要 Spawn proximity？

- Disagreement：commands.md 要求 Spawn 1 格内；game_api.idl.yaml/Registry 将 Recycle 描述为 self-action no spawn proximity。
- Speaker 裁决：需用户在 D6 确认；Speaker 推荐 **no spawn proximity**。
- 理由：self-action schema 只有 object_id，若要求 proximity 需要额外 target/validation 语义；多数 cross-cutting reviewer 建议以 IDL self-action 方向统一。

### CR6 — Storage tax 应保持 tiered step 还是改连续函数？

- Disagreement：GLM 认为 tiered 公式设计成熟但算术需修；DSV4 指出 tier boundary discontinuity 会造成 threshold oscillation；GPT 强调人类尺度解释缺失。
- Speaker 裁决：需用户在 D9 确认；Speaker 推荐 **保留 tiered step，但补 hysteresis/平均税基/解释层，避免微操 oscillation**。
- 理由：直接替换连续函数会改变已有设计面；先证明或约束 step function 的边界行为更符合“设计即目标状态”的最小一致修复。

## 方向专属 High

### Architecture High

| ID | 来源 | 问题 | Speaker 处置 |
|---|---|---|---|
| A-H1 | rev-dsv4-architect | `TickInputEnvelope` 残留 `wasm_status`，与 `terminal_state` 7-variant/22-field Registry 不一致 | P1；字段级对齐；若属于 B1 codegen 表，则一并修 |
| A-H2 | rev-dsv4-architect | `InsufficientResource` refund 表重复且语义矛盾 | P1；拆分 debug_detail/触发条件，避免 wire enum 膨胀 |
| A-H3 | rev-glm-architect | S03 build_system HitPoints=W 与 S15/S24 HP writer contract 冲突 | P1；确认 construction HP 初始化 writer |
| A-H4 | rev-glm-architect | `host_path_find` fuel cost 可能在正常场景挤压 10M budget | P1/P2；若为策略压力需写明，不然调低或改成本模型 |
| A-H5 | rev-gpt-architect / rev-gpt-cross | Mod 静态编译与下一 tick upgrade/disable 抽象断裂 | P1/D5；需用户裁定模型 |
| A-H6 | rev-gpt-architect | Gateway 技术栈 Rust/axum vs Go stateless 图示冲突 | P1；auto-align 到已裁定技术栈或提出 D-item（若用户要换栈） |

### Design & Economy High

| ID | 来源 | 问题 | Speaker 处置 |
|---|---|---|---|
| E-H1 | rev-gpt-design / rev-dsv4-design / rev-glm-design | Early/mid self-sustain target curve 与 Resource Ledger/Balance Sheet/PLAYTEST-GATED 冲突 | P0；并入 B5 |
| E-H2 | rev-gpt-design | BuildCost 权威数值冲突（PowerSpawn/Nuker/Depot 数量级不同） | P0；auto-align 到 Resource Ledger canonical cost 表，若缺表则新增 |
| E-H3 | rev-dsv4-design | Anti-snowball proof 缺形式化边际收益/成本与稳定均衡 | P1；补公式性质与参数范围 |
| E-H4 | rev-dsv4-design / rev-glm-design | Storage tax discontinuity + 算术错误 + capacity 非单调 | P0/P1；先修算术，再处理 D9 |
| E-H5 | rev-dsv4-design / glm-design | Drone lifecycle/recycle/MIN_LIFESPAN/per-drone upkeep 权威参数缺失 | P1；补 Resource Ledger 或 Gameplay 权威源 |
| E-H6 | rev-gpt-design / rev-dsv4-design | PvE Boss / Arena Challenge / World faucet 边界不一致 | P1/D8 |
| E-H7 | rev-dsv4-design | Transport intercept payoff matrix / escort equilibrium 未定义 | P1；补 payoff matrix 或裁定为 empirical calibration |

### Cross-Cutting High

| ID | 来源 | 问题 | Speaker 处置 |
|---|---|---|---|
| X-H1 | rev-gpt-cross / rev-glm-cross / rev-dsv4-cross | Recycle proximity 冲突 | P0/D6 |
| X-H2 | rev-gpt-cross / glm-cross | Host function 与 MCP tool namespace 混淆 | P0；并入 B1 |
| X-H3 | rev-glm-cross / dsv4-cross | `non_idempotent_mutation` replay_class 未注册 | P0/P1；B1 子项 |
| X-H4 | rev-dsv4-cross | Swarm-Cert-Id header 存废冲突 | P0/D3 |
| X-H5 | rev-glm-cross | ClientAuthCertificate TTL 24h vs 15min–180d | P1/D7 |
| X-H6 | rev-glm-cross | Per-player drone cap 500 vs 50 | P0；B1 子项，auto-align after D1 |

## Medium / Low 处置

| 类别 | 代表项 | 处置建议 |
|---|---|---|
| 文档治理 | changelog/date/Rxx/future/deferred/计划中/远期方向 | 不作为单独 D-item；B4 下批量清理。直接闭合，不 deferred |
| 版本号 | game_api 0.4.0 vs 0.5.0；auth_api 0.1.0 vs 0.2.0 | B1 下 auto-align；由 codegen check 验证 |
| 命名 | `omitted_count` vs `omitted_counts`；host_path_find / swarm_get_path 混淆 | 直接闭合；保持 namespace 清晰 |
| TickCommitRecord 分层 | replay-critical 10 fields vs Replay identity placement | P1；补同 redb transaction 但非 replay-critical subset 的说明 |
| JSON integer boundary | JCS 允许 number，但设计禁止 f64 | P1；schema 层显式拒绝非整数 numeric literal |
| Market/Leaderboard inactive rules | visibility.md 定义 RFC-gated/不存在工具可见性 | B4 下移出 active target 或独立 RFC |
| Allied daily cap floor 表述 | balance sheet 只列 10000 floor | 直接闭合；改写公式或注明 floor/scales with receiver GCL |
| Device cap / CSR difficulty | Auth IDL 内部 5 vs 10，20 vs 24 | B2/B1 下 auto-align；无需用户决策，除非 D2 扩大 Auth surface |
| CommandAction numbering gaps | 6/7/8 reserved 未说明 | Low；加 namespace/reserved 注释即可 |
| Canonical JSON / debug float examples | debug payload 示例出现 12.53 等 | Medium；统一展示为 milli_distance 或明确 display-only |

## D-Items

### D1: Schema 单事实源层级

- 背景：B1 的根因是 IDL、Registry、codegen.md 对 canonical authority 的声明互相矛盾。
- 来源 reviewer：rev-gpt-cross-cutting F2；rev-glm-cross-cutting C1-C4/H/M；rev-dsv4-cross-cutting C2；rev-gpt-architect A-H2/A-H3。
- auto-align：否，需要用户确认长期治理方向。
- 方案A：`*.idl.yaml` 是唯一机器源；`api-registry.md` 是由 IDL/codegen 生成的人类可读 canonical publication，冲突时修 IDL 后重生成 — **推荐**。
- 方案B：`api-registry.md` 是人工 canonical source；IDL 作为派生实现输入从 Registry 反生成或手工同步 — 不推荐。
- Speaker 推荐：A。理由：SDK、ABI、CI diff 和 replay schema 需要机器可验证源；人工 Registry 继续作为唯一权威会重复本轮 drift。

### D2: Auth active surface 与证书模型

- 背景：单层 CA + 两证书模型与 auth IDL/Registry 中 Intermediate CA、admin profile、passkey/device/federation/token-era codes 冲突。
- 来源 reviewer：rev-gpt-cross-cutting F1；rev-dsv4-cross-cutting C1/H2；rev-glm-cross-cutting H2；rev-gpt-architect A-H5。
- auto-align：部分。单层 CA 与两证书是设计层已有明确立场；passkey/device/federation active surface 是否保留仍需确认。
- 方案A：严格收敛为单层 Server CA + `ClientAuthCertificate` / `CodeSigningCertificate` 两类证书；admin 是 ClientAuth scope flag；恢复只保留已裁定 email optional；passkey/device/federation 不进入 active Auth API — **推荐**。
- 方案B：把 passkey/device/federation/admin-short-lived profile 纳入目标 Auth surface，并同步扩展 design/auth.md — 不推荐，除非用户明确要扩大 Auth 控制面。
- Speaker 推荐：A。理由：最小暴露面更符合应用层证书架构；也能最大幅度清除旧模型残留。

### D3: `Swarm-Cert-Id` header 存废

- 背景：design/auth.md 与 auth_api.idl.yaml 列出 `Swarm-Cert-Id` header；api-registry.md 移除该 header 并称 cert_id 从 certificate body 读取。
- 来源 reviewer：rev-dsv4-cross-cutting C4；rev-glm-cross-cutting相关 Auth signature findings。
- auto-align：否，两种请求格式都可实现，需要裁定 wire contract。
- 方案A：保留 `Swarm-Cert-Id` header；Gateway 校验 header id 必须与证书 body 匹配，签名 payload 覆盖该 header — **推荐**。
- 方案B：移除 header，仅从 certificate body 解析 cert_id；所有文档删除 header 字段。
- Speaker 推荐：A。理由：显式 header 有利于 lookup/routing/audit，但必须加一致性校验防止 header/body mismatch。

### D4: Deploy activation 是否依赖 raw WASM blob upload

- 背景：B3 显示 activation 条件在 `upload_status == complete` 与 compiled artifact ready 之间冲突。
- 来源 reviewer：rev-gpt-architect A-H3；rev-gpt-cross-cutting F3；rev-glm-cross-cutting C4/L3；rev-dsv4-architect CX4。
- auto-align：部分。多数架构文档与 reviewer 推荐 redb manifest + compiled artifact。
- 方案A：activation 只依赖 redb deploy manifest + compiled artifact；raw WASM blob/object store 是审计归档，pending/failed 只产生 audit gap，不使 deploy FAILED — **推荐**。
- 方案B：raw WASM blob upload complete 是 activation 必要条件；object store 可用性进入 deploy critical path。
- Speaker 推荐：A。理由：更符合 replay-critical subset 与 object-store 非权威分层；避免 I/O 状态破坏 deterministic activation。

### D5: Mod 生命周期模型

- 背景：文档同时说 Mod 是 Bevy Plugin 静态编译进 Engine，又说 `swarm mod upgrade/disable` 下一 tick 生效。
- 来源 reviewer：rev-gpt-architect A-H4；rev-gpt-cross-cutting F7。
- auto-align：否，需要用户确认扩展机制目标。
- 方案A：静态编译模型：`mod add/upgrade/disable` 修改 lock/config/source；生效需要 rebuild + Engine restart，在明确 tick boundary 切换 binary + system_manifest_hash；disable 是 world.toml gating 或重启后移除 — **推荐**。
- 方案B：tick 级 hot-swap：设计动态 plugin ABI、state migration、loaded module isolation、replay lock。
- Speaker 推荐：A。理由：现有技术选择是 Bevy Plugin 静态引入；B 是大规模新架构，不应隐含在一句“下一 tick 生效”里。

### D6: Recycle 是否要求 Spawn proximity

- 背景：commands.md 要求 drone 在 Spawn 1 格内；game_api.idl.yaml/Registry 说 self-action no spawn proximity required。
- 来源 reviewer：rev-gpt-cross-cutting F5；rev-dsv4-cross-cutting C3；rev-glm-cross-cutting M10。
- auto-align：否，影响 gameplay 语义与 recycle 策略。
- 方案A：Recycle 是 self-action，无 Spawn proximity；只需 `object_id` + ownership/visibility/eligibility 校验 — **推荐**。
- 方案B：Recycle 必须在 Spawn 1 格内；IDL/Registry 增加 proximity validation 说明，必要时增加 target_spawn_id 或明确隐式 nearest spawn。
- Speaker 推荐：A。理由：当前 schema 已按 self-action 建模；A 更直观且减少路径依赖。若用户想强化物流/撤退成本，可选 B，但必须重写 schema。

### D7: ClientAuthCertificate TTL 默认值与上限

- 背景：design/auth.md 写 24h；auth IDL/Registry 写 15min–180d。180d 私钥泄露窗口需要安全裁定。
- 来源 reviewer：rev-glm-cross-cutting H3；rev-dsv4-cross-cutting Auth findings。
- auto-align：否，属于安全策略。
- 方案A：默认 24h，允许较窄 world.toml 范围（例如 15min–7d 或用户另定），长会话靠 renew；admin scope 更短 — **推荐**。
- 方案B：保留 15min–180d 宽范围，由服务器运营者自行配置。
- Speaker 推荐：A。理由：默认 24h 与设计已有文字一致；收窄上限降低证书泄露风险，revocation 不应成为长期 TTL 的唯一防线。

### D8: PvE Boss / Arena Challenge / World faucet 边界

- 背景：World PvE 说多阶段 Boss 属于 overhaul mod；Arena PvE Challenge 又包含官方 Boss 场景；Resource Ledger 有 Boss Drone 奖励层级。
- 来源 reviewer：rev-gpt-design-economy D-ECO-3；rev-dsv4-design-economy C6。
- auto-align：否，影响官方内容边界。
- 方案A：World 持久生态不内置深度 Boss；Arena Challenge 可提供隔离官方 Boss 场景，但不产出 World 资源，不进入 World PvE faucet — **推荐**。
- 方案B：Boss/multi-stage AI 全部属于 mod；官方 Arena `Ruin Siege` 改为非 Boss Guardian/Ruin challenge。
- Speaker 推荐：A。理由：保留 Arena 作为可复现测试场的教学/挑战价值，同时不污染持久 World 经济。

### D9: Storage tax tier function 形态

- 背景：DSV4 指出 tier threshold step function 会产生 oscillation；GPT/GLM 指出解释层与算术可审计性不足，但 GLM认可 tiered fixed-point公式方向。
- 来源 reviewer：rev-dsv4-design-economy C2；rev-gpt-design-economy D-ECO-4；rev-glm-design-economy 2.2/2.3/3.2。
- auto-align：否，改变税函数会改变经济策略。
- 方案A：保留 tiered step tax，但补充 hysteresis、average-over-window 或 bounded oscillation proof，并加入 per-100/per-1000 tick 人类尺度解释 — **推荐**。
- 方案B：改为连续 marginal rate function（quadratic/sigmoid）或 integral-based taxation，消除阈值跳变。
- Speaker 推荐：A。理由：最小化机制重写；先证明/约束现有机制即可闭合策略风险。若用户更重视数学平滑，可选 B。

### D10: Drone message system 是否进入 tick() contract

- 背景：gameplay 描述 `TickResult = { commands, messages }`，但 api-idl tick() contract 只返回 CommandIntent[]；消息还可能支持 peer-to-peer resource exchange proposal，触及 Resource Ledger 单入口原则。
- 来源 reviewer：rev-glm-design-economy 2.7/CX1。
- auto-align：否，接口与经济边界都受影响。
- 方案A：消息系统进入正式 TickResult schema，但仅作为无经济副作用的 communication intent；任何资源交换必须转化为 Transfer Gateway 审计命令 — **推荐**。
- 方案B：移除 gameplay 中的 drone message 设计，或改为独立 MCP/host/query 非经济功能，不进入 tick() ABI。
- Speaker 推荐：A。理由：保留协作表达能力，同时不允许 message payload 绕过 Resource Ledger。

## 亮点汇总

1. COLLECT/EXECUTE 分层得到三方向广泛认可，是本轮最稳定的架构资产。
2. Shadow Write + Atomic Publish 被多名 reviewer 认为是持久化模型中最精致、最关键的改进。
3. Resource Flow Classification + Transfer Gateway 单入口为经济审计与 deterministic replay 提供了良好底座。
4. fixed-point type registry 在 IDL/Registry 层获得一致正面评价，是确定性系统的重要基石。
5. ActionRegistry dispatch 模式被 Cross-Cutting 认可为干净的扩展边界：核心 CommandAction 稳定，vanilla/mod action 可注册。
6. visibility `is_visible_to` 单函数 oracle 防线、omitted_count 分桶、特殊攻击拒绝码等价类获得架构向高度肯定。
7. Arena vs World 的总体定位被认可：World 接受持久不公平，Arena 追求隔离、公平、可复现。
8. 新手保护与 AI agent feedback loop 的方向正确：safe_mode/soft_launch、dry_run/explain/deploy_status 等能把“写代码玩 RTS”的学习曲线降下来。

## 改进建议优先队列

### P0 — 必须先修，修完才值得下一轮 clean-slate review

1. B1：裁定并修复 IDL/Registry/codegen 单事实源；跑生成 diff，消除全部 schema/ABI/error/deploy/version/capacity drift。
2. B2：统一 Auth CA/cert/tool surface；移除 Intermediate CA/token-era/admin-profile 残留；裁定 Swarm-Cert-Id 与 TTL。
3. B3：统一 Deploy 状态机；IDL 改为同步 deploy_mutation；activation 条件与 persistence contract 对齐。
4. B4：从 design/spec/reference active 目标文档中清理 future/deferred/Phase/changelog/date/Rxx/计划中/远期方向等治理违规文本。
5. Recycle proximity 冲突（D6）必须裁定并同步 commands.md / IDL / Registry / engine death path。
6. Economy balance sheet 的确定性算术错误必须修复：free_upkeep 记账、20-room storage tax、10/50-room taxable intermediate values、storage_capacity 非单调、per-drone upkeep 未定义。

### P1 — 第二优先级，影响设计可信度和实现直觉

1. Anti-snowball proof 从定性断言升级为边际收益/成本、稳定均衡和参数范围说明。
2. Storage tax 解释层与 threshold oscillation 处理（D9）。
3. BuildCost canonical 表、self-sustain growth path、PLAYTEST-GATED/Empirical Calibration Requirements 对齐。
4. Drone lifecycle 参数权威源：MIN_LIFESPAN、BASE_AGE、active_aging、drone_decay_rate、Recycle break-even、repair/recycle strategy。
5. PvE Boss/Arena/World faucet 边界（D8）与 PvE budget zone equilibrium。
6. Mod lifecycle 静态编译 vs hot-swap 裁定（D5）。
7. TickInputEnvelope `terminal_state`、TickCommitRecord replay identity、JSON integer-only schema、S03 HP writer contract 等 engine/spec 对齐。
8. Host function vs MCP namespace 拆分；transport/audience/capability label registry。

### P2 — 可批量闭合，但不应长期遗留

1. 命名一致性：`omitted_count`、host_path_find、redb_version_counter vs version_counter。
2. inactive/RFC market/leaderboard visibility rules 移出 active target 或独立 RFC。
3. Allied daily cap floor 表述、TransferToGlobal/FromGlobal vs AlliedTransfer fee taxonomy。
4. CommandAction numbering gap 与 namespace 前缀说明。
5. Onboarding ladder、World/Arena/PvE recognition matrix、人类尺度经济 dashboard 表述。

---

## 9. D-Item 用户裁决结果

| D-Item | 主题 | 用户选择 | 方案 |
|--------|------|----------|------|
| D1 | Schema 单事实源层级 | A | `*.idl.yaml` 为唯一机器源，Registry 由 codegen 生成 |
| D2 | Auth active surface | A | 单层 Server CA + 两证书，passkey/device/federation 不进 Auth API |
| D3 | Swarm-Cert-Id header | A | 保留 header，Gateway 校验与证书 body 匹配 |
| D4 | Deploy activation | A | 仅依赖 redb manifest + compiled artifact（auto-align） |
| D5 | Mod 生命周期 | A | Bevy Plugin 静态编译，upgrade/disable 需 rebuild + restart |
| D6 | Recycle proximity | A | self-action，无 Spawn proximity |
| D7 | ClientAuthCertificate TTL | A | 默认 24h，范围 15min–7d |
| D8 | PvE Boss / Arena 边界 | B | Boss 属于 mod，vanilla 自带 boss plugin 引入 World + Arena |
| D9 | Storage tax tier function | B | 改为连续边际税率函数，消除阈值跳变 |
| D10 | Drone message system | A | 进入 TickResult schema，纯通信无经济副作用，资源交换走 Transfer Gateway |

裁决人：神楽坂喵 | 日期：2026-06-30 | 轮次：R43

## Overall Verdict

**REQUEST_MAJOR_CHANGES**

裁决理由：R43 文档的核心设计方向值得保留，但当前存在 5 个 Blocker 级问题，其中 B1/B2/B3 是 machine-readable / security / deploy contract 硬冲突，B4 是仓库目标状态治理的系统性违规，B5 是经济数学闭环不足。修复应先从单事实源、Auth、Deploy、文档治理与经济算术开始；D-items 需要用户逐项裁决或确认推荐方向后，才能进入修复阶段。
