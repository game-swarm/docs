# R41 Speaker 裁决

## §1 裁决概要

整体 Verdict: REQUEST_MAJOR_CHANGES

统计矩阵：
- APPROVE: 0/9
- CONDITIONAL_APPROVE: 3/9（rev-glm-architect, rev-glm-design-economy, rev-dsv4-cross-cutting）
- REQUEST_MAJOR_CHANGES: 6/9（rev-gpt-architect, rev-dsv4-architect, rev-gpt-design-economy, rev-dsv4-design-economy, rev-gpt-cross-cutting, rev-glm-cross-cutting）
- REJECT: 0/9

Speaker 结论：R41 文档集已有成熟的确定性 tick、WASM sandbox、visibility oracle、Resource Ledger、ActionRegistry 与 replay 分层设计；但 9 份报告共同显示，当前 clean-slate 文档仍存在多处会直接误导实现的跨文档目标状态冲突。按议会规则，≥2 方向 + ≥2 模型共同标记的问题提升为共识 Blocker。本轮不可进入修复后提交前的 approve 状态，需先统一 B1-B6 与 D-items。

缺失报告：无。任务要求 9 份 Phase 1 报告，已全部读取并纳入。

## §2 共识 Blocker

### B1 — Critical — 模组/扩展机制目标架构冲突：Bevy Plugin 唯一机制 vs Rhai/RuleMod

来源 reviewer：
- Architect: rev-gpt-architect A-H3；rev-dsv4-architect C3；rev-glm-architect ARCH-H2
- Cross-Cutting: rev-gpt-cross-cutting C1；rev-dsv4-cross-cutting C3；rev-glm-cross-cutting CC-1

文件引用：
- design/engine.md:11-12
- design/tech-choices.md:48-87, 200-208
- specs/security/09-command-source.md:31-32, 47-48, 178-179, 303-309
- specs/core/01-tick-protocol.md §9.8
- specs/core/07-world-rules.md:7-15, 312-392
- specs/reference/rhai-mod-abi.md:1-4

问题描述：engine.md 与 tech-choices.md 明确声明 Mod = Bevy Plugin 静态编译进 Engine，Rhai 已移除，且这是唯一扩展机制；但 command-source、tick-protocol、world-rules、rhai-mod-abi 仍保留完整 Rhai RuleMod source、Rhai op budget、RhaiActionBuffer、hook/capability/ABI 合同。

影响范围：Engine mod loading、world.toml 规则系统、Command Source、Source Gate、replay manifest、ActionRegistry hash、mod packaging、CI、security sandbox。两套模型的执行边界、信任模型、部署方式完全不同，不能同时作为无解释的“当前设计”。

修复方向建议：见 D1。必须先裁决：纯 Bevy Plugin；或 Rhai RuleMod 与 Bevy Plugin 分层并存。裁决后统一删除/重写另一套表述，不允许继续保留“唯一机制”与“完整 Rhai ABI”并存。

### B2 — Critical — 已移除基础设施 Dragonfly/ClickHouse 在 README、tick、visibility、MCP/security 中残留

来源 reviewer：
- Architect: rev-gpt-architect A-H1/A-H9；rev-dsv4-architect C1/C2/H2/H3；rev-glm-architect ARCH-H1
- Cross-Cutting: rev-gpt-cross-cutting C2；rev-dsv4-cross-cutting C2；rev-glm-cross-cutting CC-6

文件引用：
- design/README.md:131-136, 170-175
- design/tech-choices.md:134-155
- specs/core/01-tick-protocol.md:115, 623-634, 657-658, 748
- specs/security/05-visibility.md:204-219
- specs/security/03-mcp-security.md:374-392

问题描述：tech-choices 已裁定 Dragonfly 被 Engine 内 Moka Cache 替代、ClickHouse 被 redb metrics table + Gateway aggregation 替代；但 README 架构图/数据模型、tick BROADCAST、visibility 查询源、MCP audit DDL 仍引用 Dragonfly、ClickHouse 或 MergeTree。

影响范围：部署拓扑、缓存一致性、BROADCAST fan-out、审计日志保留、运维 runbook、故障模型。入口 README 与核心 specs 误导实现者部署已移除组件。

修复方向建议：全局搜索 Dragonfly/ClickHouse/MergeTree。README 数据层改为 redb + object store/append-only log（如仍存在）+ Gateway 聚合；Moka 作为 Engine 进程内 cache 标注在 Engine 框内；MCP audit 改为 redb audit/metrics table 或 object-store append-only log + redb pointer/hash。若确实恢复 ClickHouse，必须反向修改 tech-choices 并重裁。

### B3 — Critical — Auth 证书/CA/信任模型冲突：2 类证书 + 单层 Server CA vs Admin/Federation + Root/Intermediate

来源 reviewer：
- Architect: rev-gpt-architect A-H2
- Cross-Cutting: rev-gpt-cross-cutting C4/C10；rev-glm-cross-cutting CC-2/CC-7/CC-8/CC-10

文件引用：
- design/auth.md:31-33, 104-125, 181-186, 220-228
- design/tech-choices.md:207-208
- specs/security/09-command-source.md:20-21, 66-68, 112-113, 132
- specs/security/03-mcp-security.md:46-54, 198-220
- specs/reference/api-registry.md:413, 417-425, 636-653, 786-803
- specs/reference/mcp-tools.md:84-93

问题描述：auth.md/tech-choices 声明单层 Server CA，且证书类型仅 ClientAuthCertificate 与 CodeSigningCertificate；Admin 通过 ClientAuth + admin scope 表达，Federation 不需独立证书。但 command-source、mcp-security、api-registry、mcp-tools 仍保留 AdminCertificate/FederationCertificate、Server Root/Intermediate CA、intermediate_ca_fingerprint、leaf+intermediate certificate chain 等旧模型。

影响范围：证书 envelope、auth_api codegen、scope/audience 校验、renew/revoke、trust pinning UI、admin/federation 操作授权、CRL/epoch bump、安全审计。该问题是安全根与能力模型冲突，必须阻塞。

修复方向建议：见 D3。若以 auth.md 为准，删除 AdminCertificate/FederationCertificate 类型，Admin/Federation 统一为 ClientAuth scopes / identity mapping；Root/Intermediate 术语统一为 Server CA；API 字段改为 server_ca_fingerprint/server_ca_certificate；Certificate-Chain 不再含 intermediate。

### B4 — High — Gateway 实现语言与边界冲突：Go vs Rust

来源 reviewer：
- Architect: rev-gpt-architect A-H1；rev-dsv4-architect H1
- Cross-Cutting: rev-gpt-cross-cutting C3；rev-dsv4-cross-cutting C1；rev-glm-cross-cutting CC-5

文件引用：
- design/README.md:82-87, 154, 202
- design/auth.md:51-57, 90-97

问题描述：README 将 Gateway 标为 Go，仓库结构也写 gateway/ Go API 网关；auth.md 架构图将 Gateway 标为 Rust，并将 Certificate Auth handler、CSR/renew 等安全职责放在该 Gateway 中。

影响范围：Gateway repo/module 边界、证书校验库、REST/gRPC/WS/MCP auth middleware、安全审计语言栈、CI/lint、部署职责。虽然不一定改变游戏规则，但会直接影响实现组织。

修复方向建议：见 D2。必须单选并全局统一：Rust Gateway；或 Go Gateway + Rust/Auth sidecar/service 明确边界。

### B5 — High — CommandAction / IDL / API Registry / RejectionReason 合同漂移

来源 reviewer：
- Architect: rev-gpt-architect A-H5；rev-glm-architect CrossCheck CX-1/CX-2
- Design & Economy: rev-glm-design-economy DE-1/DE-2/DE-8/DE-9/DE-10；rev-dsv4-design-economy M2/CX-3
- Cross-Cutting: rev-gpt-cross-cutting C5/C9；rev-glm-cross-cutting CC-13/CC-14

文件引用：
- specs/core/02-command-validation.md:223-256, 289-428, 655-704
- specs/core/06-phase2b-system-manifest.md:88-93
- specs/gameplay/08-api-idl.md:67-149, 189-233
- specs/reference/api-registry.md §1, §2, §10

问题描述：R35 D3 后 combat/special actions 应通过 CommandAction::Action + ActionRegistry dispatch；但 command-validation 仍展示 Attack/Heal/Hack 等旧顶层命令形态。IDL 的 RejectionReason enum 与 API Registry canonical 48/49 codes 脱节；IDL CommandAction 仍写“19 指令”，且 TransferToGlobal/TransferFromGlobal 分类、Spawn/Recycle 参数、tick() 返回格式、refund_policy 均与 Registry 或 design/interface 不一致。

影响范围：wire schema、SDK/codegen、canonical serialization、command_hash、Source Gate、replay/TickTrace、validator 实现。若不统一，同一动作会存在多种编码或错误 enum，破坏确定性与 API 稳定性。

修复方向建议：指定机器权威源并闭合生成链。command-validation §3 只保留基础 CommandAction；Attack/RangedAttack/Heal/8 special attacks 全部改为 ActionRegistry handler。IDL enum/params/return shape 与 Registry 完全同步；若 Registry 由 YAML 生成，必须把 YAML 纳入评审包并由 CI diff gate 防漂移。

### B6 — High — Controller/Depot age repair 与 50% 全局 repair cap 冲突

来源 reviewer：
- Design & Economy: rev-gpt-design-economy D&E-2；rev-dsv4-design-economy C2；rev-glm-design-economy DE-12
- Cross-Cutting: rev-gpt-cross-cutting C8；rev-dsv4-cross-cutting M2/CX-4

文件引用：
- design/gameplay.md:102, 437, 523-525
- design/engine.md:452-463
- specs/core/07-world-rules.md:828-848
- specs/core/08-resource-ledger.md:152-166
- specs/reference/api-registry.md:561-563
- design/economy-balance-sheet.md:220-223

问题描述：engine.md、Resource Ledger、API Registry 多处声明无全局 repair cap，age repair 免费，仅受 repair_range、repair_capacity、queue/physical distribution 限制；但 gameplay/world-rules 仍保留“每 tick 总 age 回退 ≤ 自然增长 50%”硬上限，以及 repair distance decay 等旧参数。

影响范围：drone 生命周期、Controller/Depot 升级收益、前线补给策略、新手学习曲线、经济平衡、实现是否需要跨 Controller 全局聚合。此处改变的是 core gameplay，不是措辞。

修复方向建议：见 D4。裁决后同步 gameplay、engine、world-rules、resource-ledger、api-registry、economy-balance-sheet。若采用无全局 cap，删除 50% cap 和 distance decay；若采用 50% cap，则写入 Resource Ledger 权威公式并定义自然增长口径。

## §3 方向专属发现

### Architect 专属 High/Medium

- A-H1 — Spawn / PendingEntityCreation / SpawningGrace 时序合同互相矛盾。来源：rev-gpt-architect A-H4。建议采用 PendingEntityCreation 纯净模型，新实体下一 tick 可交互，grace 改为创建时携带并在首次可交互 tick 生效。
- A-H2 — Deploy 在 RawCommand ordering 中先于 WASM，与 activation_tick >= current_tick+1 冲突。来源：rev-gpt-architect A-H6、rev-glm-architect CX-1。建议 Deploy 移出 gameplay RawCommand queue，作为控制面 mutation，最早 N+1 生效。
- A-H3 — TickCommitRecord 字段数/Envelope 边界不一致（10 vs 13/18+）。来源：rev-glm-architect ARCH-H3。建议区分 replay-critical core、replay identity、TickInputEnvelope。
- A-M1 — deterministic replay 与 Object Store/RichTraceBlob 依赖描述混乱。来源：rev-gpt-architect A-H7。建议拆分 deterministic replay 与 rich debug replay。
- A-M2 — snapshot 不可截断关键实体可能超过 256KB cap。来源：rev-dsv4-architect M3。建议定义 over-budget 降级和最小保留集合。
- A-M3 — seccomp clock_gettime/write 与 Wasmtime epoch interruption/输出模型需验证。来源：rev-glm-architect ARCH-M3。
- A-M4 — Resource 使用 IndexMap<String,u32> 的插入顺序确定性需声明，或改 BTreeMap。来源：rev-glm-architect ARCH-M4。
- A-M5 — WASM 缺少 host_get_fuel_remaining，玩家无法主动控制 fuel。来源：rev-glm-architect ARCH-M5。

### Design & Economy 专属 High/Medium

- D-H1 — economy-balance-sheet storage tax 算术错误。来源：rev-gpt-design-economy D&E-1、rev-dsv4-design-economy C1。10-room 45 应为 75；20-room 120 应为 180；50-room 600 应为 765。需按 Resource Ledger tiered formula 重算并建议脚本校验。
- D-H2 — Global↔local transfer intercept 未覆盖非 Allied 路径。来源：rev-dsv4-design-economy C3。见 D5。
- D-H3 — 1-room free_upkeep 结束后死亡螺旋窗口可能过窄。来源：rev-dsv4-design-economy H1。建议补 1→2 room transition analysis。
- D-H4 — Fabricate cost 800 vs 2000、body part Work vs Work+Carry、Leech resistance Kinetic vs Corrosive。来源：rev-dsv4-design-economy M2、rev-glm-design-economy DE-3/DE-4/DE-5。建议以 ActionRegistry/special-attack-table 作为权威，消除重复表。
- D-H5 — allied_daily_cap 动态公式 vs 固定 10,000。来源：rev-glm-design-economy DE-6、rev-dsv4-design-economy M3。建议统一为 Resource Ledger 公式 max(10_000, receiver_gcl × 20_000) 并传播 multiplier。
- D-M1 — Snapshot Contract storage tax “0.1%/tick” 与 tiered formula 冲突。来源：rev-gpt-design-economy D&E-4。
- D-M2 — World PvE 默认 Crystal/Blueprint 与 Vanilla 单 Energy 学习路径冲突。来源：rev-gpt-design-economy D&E-6。
- D-M3 — tick() 返回格式 commands vs {commands,messages} vs pointer/i32。来源：rev-glm-design-economy DE-9。
- D-M4 — Balance Sheet storage_capacity 在 20-room 小于 10-room，公式无解释。来源：rev-glm-design-economy DE-7。

### Cross-Cutting 专属 High/Medium

- C-H1 — API Registry 声称由 IDL YAML 生成，但评审包缺失 game_api.idl.yaml/auth_api.idl.yaml/economy.idl.yaml。来源：rev-gpt-cross-cutting C5。建议纳入评审/实现输入或改写权威声明。
- C-H2 — 跨文档相对链接错误、docs/ vs 扁平根路径假设不一致。来源：rev-gpt-cross-cutting C6；rev-dsv4-cross-cutting H1/H2。建议统一根路径并加入 markdown-link-check。
- C-H3 — 建造成本在 07-world-rules 与 API Registry 大规模不一致。来源：rev-glm-cross-cutting CC-9。建议以 IDL/Registry 权威源统一并补齐 Road/Wall/Rampart/Container/Depot 等。
- C-H4 — Canonical Request Signature headers 不一致，多出/缺少 Swarm-Cert-Id，Certificate-Chain 暗示 intermediate。来源：rev-glm-cross-cutting CC-10。
- C-M1 — world.toml 使用 f64，但 Registry 固定点类型要求 No f64。来源：rev-glm-cross-cutting CC-11。
- C-M2 — host_get_random fuel cost 在 Registry 与 host-functions.md 不一致。来源：rev-gpt-cross-cutting C9。
- C-M3 — special attack 数量表不完整，world-rules §7.8 缺 Leech/Fabricate。来源：rev-gpt-cross-cutting C7；rev-glm-cross-cutting CC-15。
- C-M4 — 07-world-rules register_systems 示例与 31-system manifest 不匹配。来源：rev-glm-cross-cutting CC-16。

## §4 D-items

### D1: 模组系统最终目标架构

背景：B1。文档同时声明 Bevy Plugin 是唯一扩展机制、Rhai 已移除；又维护完整 Rhai RuleMod ABI。

方案A：纯 Bevy Plugin。RuleMod/Rhai 全部删除或归档；07-world-rules 改写为 Rust Plugin + manifest/action registry；Command Source 不再有 RuleMod source。优点是安全边界简单、与 engine/tech-choices 当前文字一致；缺点是会废弃已有 Rhai ABI 设计。

方案B：分层并存。Engine/内置 mod 使用 Bevy Plugin 静态编译；世界规则/复杂变体使用受限 Rhai RuleMod，tech-choices 改成“玩家脚本 Rhai 已移除，RuleMod Rhai 仍是 world rules 扩展层”。优点是保留复杂变体的可配置性；缺点是必须重新定义 Rhai 与 Bevy 的安全/确定性边界。

Speaker 推荐：B，但必须写成严格分层，而不是两个“唯一机制”并存。理由：Cross-Cutting 报告指出 Rhai ABI 已有完整事务/能力/预算合同；若用户目标仍需要 world-rule mod 灵活性，分层模型比删除整套 ABI 更符合“核心机制目标状态 + mod 扩展复杂度”。若用户确认不再要 Rhai，则改采 A。

### D2: Gateway 实现语言

背景：B4。README 为 Go，auth.md 为 Rust。

方案A：Gateway 统一 Rust。Auth handler、Ed25519/CSR、certificate middleware 与 Engine Rust 生态直接共享类型/库。

方案B：Gateway 统一 Go。保持 README/gateway 目录设定；auth 功能通过 Rust Auth Service/sidecar/gRPC 或 Go 原生库实现，并明确边界。

Speaker 推荐：A。理由：当前冲突主要集中在证书、安全中间件与 Gateway 绑定，Rust Gateway 可减少跨语言证书解析与签名 canonicalization 分叉。但若实际仓库已有 Go Gateway 代码基础，用户可裁决 B，随后 auth.md 需要拆出 Auth Service 边界。

### D3: Auth 证书类型与 CA 模型

背景：B3。2 类证书 + 单层 Server CA vs 4 类证书 + Root/Intermediate。

方案A：坚持 auth.md/tech-choices：仅 ClientAuthCertificate + CodeSigningCertificate；Admin/Federation 通过 ClientAuth scopes/audience/identity mapping；单层 Server CA。

方案B：恢复 API Registry 4 类证书：ClientAuth、CodeSigning、Admin、Federation，并恢复/明确 Root/Intermediate 或兼容链模型。

Speaker 推荐：A。理由：多份安全设计已把 4 类证书与 Root/Intermediate 标为旧模型；2 类证书 + scope 更小权限、更少 schema/codegen 分叉。执行时需同步 Registry、MCP tools、command-source 与 header schema。

### D4: Controller/Depot age repair 是否有 50% 全局上限

背景：B6。无全局 cap 的物理约束模型与 50% 总 age 回退硬上限冲突。

方案A：无全局 repair cap。Repair 免费，受 repair_range、repair_capacity、queue、物理分布限制；删除 50% cap 与 distance decay。

方案B：保留 50% 全局硬上限。Resource Ledger 定义精确公式、自然增长口径、跨 Controller/Depot 聚合规则与 TickTrace 归因。

Speaker 推荐：A。理由：该方案与 engine.md、Resource Ledger、API Registry 的当前权威语义一致，复杂度更低，也避免引入全局聚合状态；anti-snowball 可由 upkeep/storage tax/物流/repair queue 承担。

### D5: Global↔local transfer 是否也可拦截

背景：D-H2。gameplay 承诺 global↔local transport 可被拦截，但 snapshot-contract 只定义 Allied Transfer intercept。

方案A：Global deposit/withdraw 与 Allied Transfer 都进入 Transport Intercept Contract，定义各自 delay/window/success formula/ledger attribution。

方案B：核心只支持 Allied Transfer intercept；global deposit/withdraw 延迟不可拦截。gameplay.md 修正为“仅 Allied Transfer 可被拦截”，完整物流战作为 mod/扩展规则。

Speaker 推荐：B。理由：当前已有确定性 Allied Transfer intercept 合同；把 global storage 也纳入拦截会显著扩大物流战规则面，需要额外 ledger op、snapshot exposure、attack surface 与新手体验校准。若用户希望核心物流战更彻底，可裁决 A，但必须同时补 Resource Ledger 的 InterceptAward/Fail 归因。

### D6: PoW challenge 难度策略

背景：rev-glm-cross-cutting CC-3。auth.md 写 adaptive 20-32 bits；API Registry 写 fixed 24 bits/default 24 bits。

方案A：固定 24 bits。Registry 为准，auth.md 改为固定默认/固定策略。

方案B：自适应 20-32 bits。auth.md 为准，Registry schema 改为返回当前 difficulty_bits，并定义调节算法与审计字段。

Speaker 推荐：A。理由：固定 24 bits 更易于 codegen、测试和用户文档一致；若未来需要 adaptive，可作为明确配置项而非当前冲突状态。

## §5 CrossCheck 追踪

无 Phase 2 补充评审报告。本节仅记录 Phase 1 报告提出、需后续专项检查的 CrossCheck 项：

- CX-AUTH：集中检查 auth.md、api-registry.md、mcp-tools.md、command-source、mcp-security 中 Admin/Federation、Root/Intermediate、passkey、PoW、TTL、headers、nonce/signature canonicalization。
- CX-API：检查 IDL YAML 是否存在并纳入包；IDL ↔ Registry ↔ generated docs 是否由 CI diff gate 强制一致。
- CX-ACTION：检查 special-attack-table、ActionRegistry、command-validation、world-rules 中 3 basic + 8 special 的 cost/body part/resistance/range/cooldown 一致性。
- CX-ECON：用脚本从 Resource Ledger 参数生成 economy-balance-sheet storage tax/upkeep/transfer cap，避免手算漂移。
- CX-PERF：ClickHouse 移除后，redb metrics + Gateway fan-out 是否满足 MCP/security audit 90 天查询与导出需求。
- CX-DETERMINISM：Wasmtime fuel schedule、host cost table、host_get_random、seccomp clock_gettime、cross-arch replay fixture 需实测验证。
- CX-VISIBILITY：fog_of_war=false、player_view=full、Arena 全知、Spectator 延迟全图必须通过 mode validation 防止 competitive world 误用。
- CX-DOCS：修正相对链接、docs/根路径假设、README 导航，加入 markdown-link-check。

## §6 评审统计

| Reviewer | Direction | Model | Verdict | 主要阻塞 |
|---|---|---|---|---|
| rev-gpt-architect | Architect | GPT-5.5 | REQUEST_MAJOR_CHANGES | Auth/CA, Rhai, spawn, CommandAction, deploy, replay/object-store |
| rev-dsv4-architect | Architect | DeepSeek V4 Pro | REQUEST_MAJOR_CHANGES | Dragonfly/ClickHouse/Rhai 残留, Gateway language |
| rev-glm-architect | Architect | GLM-5.2 | CONDITIONAL_APPROVE | Dragonfly/ClickHouse, Rhai, TickCommitRecord 字段 |
| rev-gpt-design-economy | Design & Economy | GPT-5.5 | REQUEST_MAJOR_CHANGES | storage tax, repair cap, Drone P2P/RCL, economy/API drift |
| rev-dsv4-design-economy | Design & Economy | DeepSeek V4 Pro | REQUEST_MAJOR_CHANGES | storage tax, repair cap, global transfer intercept |
| rev-glm-design-economy | Design & Economy | GLM-5.2 | CONDITIONAL_APPROVE | IDL/RejectionReason, CommandAction, Fabricate/Leech, allied cap |
| rev-gpt-cross-cutting | Cross-Cutting | GPT-5.5 | REQUEST_MAJOR_CHANGES | Rhai vs Bevy, README components, Gateway, Auth cert, IDL missing |
| rev-dsv4-cross-cutting | Cross-Cutting | DeepSeek V4 Pro | CONDITIONAL_APPROVE | Gateway, Dragonfly/ClickHouse, Rhai, links, repair cap |
| rev-glm-cross-cutting | Cross-Cutting | GLM-5.2 | REQUEST_MAJOR_CHANGES | Rhai, cert types, PoW/TTL, Gateway, build cost, f64 |

最终裁决：REQUEST_MAJOR_CHANGES — 6 个共识 Blocker，6 个 D-items。