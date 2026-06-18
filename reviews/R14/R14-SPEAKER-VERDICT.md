# Swarm 设计评审 R14 — Speaker 共识报告

## 裁决概要

- 本轮总览：R14 完成 14/14 Phase 1 评审（7 方向 × 2 模型）。评审信号高度集中：Swarm 的大方向被认可，但核心实现合同尚未收敛，尤其是 determinism、sandbox lifecycle、Command/API schema、FDB/TickTrace 失败语义、安全认证语义与经济参数。
- 收敛评估：当前不是功能不足导致的失败，而是“多份文档分别合理、合在一起不可实现”的合同分叉。若直接进入并行实现，会产生多个互不兼容但都可自洽的 engine / SDK / security boundary。
- Freeze 状态：**不建议 Freeze**。R14 应判定为 contract consolidation round，下一轮需在统一权威合同后重新评审。
- Phase 1 完成情况：**14/14 reviewers 完成**，无缺位、无空文件。
- Phase 2 补漏情况：本任务未等待 Phase 2。Phase 1 CrossCheck 已按目标方向汇总为补漏队列；截至本裁决写入时，未收到独立 Phase 2 报告，因此“CrossCheck 补漏发现”标注为待补漏/未执行。

## 总体 Verdict

**REQUEST_MAJOR_CHANGES**

理由：14 份报告中至少 6 份给出 REQUEST_MAJOR_CHANGES（Architect 2/2、Determinism 2/2、Security GPT、API/DX GPT），其余多数为带 Critical/High 条件的 CONDITIONAL_APPROVE。阻塞项不是孤立 bug，而是跨方向、跨模型反复命中的核心合同冲突。

## 共识 Blocker（跨方向 + 跨模型同意）

### B1: Determinism Contract 未形成唯一权威

**方向 × 模型矩阵**: Architect × GPT/DeepSeek；Determinism × GPT/DeepSeek；Performance × GPT；API/DX × DeepSeek；Security × DeepSeek CrossCheck

**问题**: 命令排序、RNG/seed、ECS 系统顺序、TickTrace 输入范围、snapshot/query 排序与 WASM 输出截断语义在多文档间分叉。最强一致信号来自 Determinism 双模型：`shuffle` 排序 vs 字典序、RNG 合同多版本、ECS chain 不闭包会直接导致 replay 不一致。

**修正要求**:
- 指定唯一 Determinism Contract 文档，删除或降级所有冲突章节。
- 冻结 command ordering：明确 shuffle 前/后、Tie-break key、TickTrace `commands_hash` 输入范围、Replay Verifier 复算路径。
- 冻结 RNG：统一算法、seed epoch、host random ABI、泄露后的恢复策略、编码规则。
- 冻结 ECS chain：列出完整 system 顺序、读写集矩阵、并行安全证明与 replay-critical 状态集合。
- 将 replay-critical 字段与 audit-only 字段拆分，避免 TickInputEnvelope 误导实现。

### B2: WASM Sandbox 生命周期与 OS 隔离边界互相冲突

**方向 × 模型矩阵**: Architect × GPT；Performance × GPT/DeepSeek；Security × GPT/DeepSeek；Determinism × GPT；API/DX × DeepSeek CrossCheck

**问题**: 文档同时描述 long-lived worker pool 与 per-tick fork/kill。安全侧依赖 fork-exec-kill 的隔离语义，性能侧指出 1000 worker RAM 与 cold-start 成本不可接受，确定性侧要求 replay envelope 知道 sandbox 生命周期与失败语义。

**修正要求**:
- 用户/架构侧裁决唯一生命周期模型：worker pool、fork-per-tick 或混合模型，不允许文档并存。
- 同步 seccomp/cgroup/namespace/clone/fork syscall 白名单与 CI checklist。
- 定义 trap/OOM/timeout/partial-output 的统一 ABI 结果：是否丢弃全部输出、是否产生 command、是否进入 TickTrace。
- 给出 500/1000 active players 的内存与冷启动预算，明确降级策略。
- 若保留 SIMD，必须定义 SIMD fuel metering 与 f64 SIMD opcode 禁止/允许策略。

### B3: Command/API/IDL/SDK 合同不可生成

**方向 × 模型矩阵**: API/DX × GPT/DeepSeek；Determinism × GPT；Economy × GPT；Designer × DeepSeek；Security × GPT CrossCheck

**问题**: Command enum、Action payload、Move 方向、错误码、host function limits、MCP tool schemas、market commands、economic commands 与 IDL 格式在多份文档间不一致。API/DX 双模型均认为这会阻断 SDK/codegen 与 AI agent 使用。

**修正要求**:
- 建立 canonical `game_api.idl` / JSON Schema / MCP schema 的唯一事实来源。
- 从 canonical schema 生成或反向校验 `commands.md`、`host-functions.md`、`mcp-tools.md`、validation matrix。
- 统一 Command enum、payload naming、Move direction、错误 envelope、RejectionReason、预算 limits。
- 为 MCP 每个 tool 补 input/output/error schema、mutation classification、rate limit、audit policy。
- 明确 Market RFC：若未冻结，不能出现在默认 IDL/SDK；若保留，必须有 validator 与经济治理合同。

### B4: FDB/TickTrace/失败语义与事务边界未闭合

**方向 × 模型矩阵**: Architect × GPT/DeepSeek；Performance × GPT/DeepSeek；Determinism × GPT；Security × GPT CrossCheck

**问题**: COLLECT 完成后到 FDB commit 前的 crash、fuel/body_cost 预扣、TickTrace 写入失败、FDB 小事务 vs 全量状态/TickTrace 入 FDB、单事务串行瓶颈等问题同时被架构、性能、确定性命中。当前设计看似 ACID，但 state、trace、object/blob/WAL 的成功条件未统一。

**修正要求**:
- 定义 tick 成功的必要条件：state commit、TickTrace manifest、object/log blob、WAL/audit 是否必须同成败。
- 明确 engine process crash 的补偿/重放/退款语义，覆盖 fuel 与 spawn body_cost。
- 约束 FDB 单事务大小，给出 room-level batching 或 manifest + blob pointer 的原子方案。
- 规定“状态成功但不可回放”是否允许；若不允许，写入 failure matrix。
- 对 TickTrace delta chain 增加完整性保护与损坏恢复策略。

### B5: 浏览器凭据、audience/transport 与 WebSocket 限流语义冲突

**方向 × 模型矩阵**: Security × GPT/DeepSeek；API/DX × DeepSeek；Architect × GPT CrossCheck；Designer × GPT CrossCheck

**问题**: Security 双模型共同命中浏览器凭据策略冲突（localStorage vs HttpOnly Cookie/WebCrypto）、transport/audience 模型不一、WebSocket 握手后消息限流过宽、CRL/证书续签/endpoint confusion 等问题。DeepSeek Security 将 localStorage 矛盾定为 Critical，GPT Security 将凭据/audience/WebSocket/OS boundary 定为 High 并给出 REQUEST_MAJOR_CHANGES。

**修正要求**:
- 删除 localStorage 持久凭据作为默认或推荐路径，统一浏览器凭据权威策略。
- 统一 audience grammar，并在 auth、MCP、Command Source 三处只保留同一版本。
- WebSocket 只免重复握手认证，不免 method/player/connection/global 限流；补 session sequence、message size、batch 禁用、backpressure。
- 定义证书续签与 tick/MCP 调用失败的交互：是否计入 trace、是否中断当前流程。
- 为 audit parameters 建立字段级 redaction/hash policy。

### B6: 经济收敛与资源账本缺少可验证基线

**方向 × 模型矩阵**: Economy × GPT/DeepSeek；Designer × DeepSeek；API/DX × DeepSeek；Determinism × DeepSeek CrossCheck；Security × GPT CrossCheck

**问题**: Economy 双模型认可资源分类框架，但指出默认 empire-upkeep 参数无法兑现 O(n²) 收敛、Recycle 依赖 upkeep 才避免套利、PvE faucet 未纳入预算、Alliance transfer 可能绕过物流/税/新玩家门、Resource Ledger 不完整。Designer/API/Determinism 也分别命中 spawning_grace+recycle、market IDL、repair→recycle 套利路径。

**修正要求**:
- 发布 Vanilla Economy Balance Sheet：统一 tick/day、source/PvE 产出、upkeep、税、转换损耗、spawn/build/recycle/refund。
- 给出 1/5/20/50 rooms、20/100/500 drones 的净流量模拟目标。
- 定义统一 Resource Ledger，覆盖 faucet/sink/transfer/lockup/unlock，禁止双花与影子转移。
- 修正默认 empire-upkeep 参数，使 superlinear 项在目标规模内真实生效。
- 明确 allied transfer、global/local transfer、market RFC、new-player gate 的默认治理策略。

### B7: Visibility / Query / Error Oracle 边界仍未完全闭合

**方向 × 模型矩阵**: Security × GPT/DeepSeek；API/DX × GPT/DeepSeek；Architect × GPT；Determinism × GPT/DeepSeek；Designer × GPT CrossCheck

**问题**: `host_get_objects_in_range`、terrain query、MCP query、snapshot truncation、`TargetNotVisible`/`NotVisibleOrNotFound`、`swarm_explain_last_tick`、replay/spectate/safe highlight 等可见性语义分布在多套接口中。若拒绝码、排序、距离基准或 debug 输出不一致，会产生实体枚举、隐藏信息反推或 replay 不一致。

**修正要求**:
- 建立统一 Query API abstraction，WASM host functions、MCP、SDK 使用同一 visibility policy 与 budget model。
- 所有命令拒绝码按 oracle-equivalence 审计，不限特殊攻击。
- 定义 terrain query、path_find、range/object query 是否受 fog-of-war 约束。
- 定义 snapshot truncation 的稳定排序、priority bucket、distance basis、hostile inflation 防滥用策略。
- Replay/观战/highlight 输出必须标注 privacy/fog/spectate_delay policy。

## CrossCheck 补漏发现（基于 Phase 2）

截至本裁决生成时，未收到独立 Phase 2 补漏报告；以下为 Phase 1 CrossCheck 队列，需作为 Phase 2 输入。状态均为 **pending Phase 2**，不能视为已验证补漏发现。

### CX1: Architect 目标方向补漏队列

**来源**: API/DX、Performance、Security、Economy、Determinism、Designer 多方向 → 目标方向: Architect

**发现**: visibility determinism、global storage delay、Arena self-play vs competitive execution、embedded Arena tick scheduling、entity cap vs economic cap、RuleMod global view、horizontal sharding trigger、simulate worker isolation、query API unification、TickTrace/FDB authority、replay-critical vs audit-only boundary。

**处置**: 高优先 Phase 2。多数已与 B1/B2/B4/B7 重叠，需在 contract consolidation 中处理；未升级的新项记录为 Architect High/Medium。

### CX2: Security 目标方向补漏队列

**来源**: Architect、API/DX、Designer、Performance、Economy、Determinism → 目标方向: Security

**发现**: seed 泄露公平性、terrain/host function 信息泄漏、SIMD fuel/f64 opcode、CRL/证书续签 tick 交互、错误脱敏侧信道、public bot/replay metadata、allied transfer 滥用、P2P payload 经济欺诈、WASM 验证队列 DoS。

**处置**: 高优先 Phase 2。凭据/WebSocket/sandbox 已升级为 B5/B2；其余作为 Security High/Medium backlog。

### CX3: Game Designer / UX 目标方向补漏队列

**来源**: Architect、API/DX、Security、Economy、Performance → 目标方向: Designer/UX

**发现**: regeneration before/after combat 的玩法含义、Move 占 main action slot 的新手心智、snapshot truncation 是否可解释/公平、spawning_grace + recycle、Replay/观战分享隐私与传播、offline self-hosted recovery UX、Broadcast stale/partial state 展示。

**处置**: Medium/High 混合。spawning_grace/recycle 与经济项升级进 B6；其余记录为设计补强项。

### CX4: API/DX 目标方向补漏队列

**来源**: Designer、Economy、Architect、Security → 目标方向: API/DX

**发现**: Market RFC 已进入 IDL、ResourceCost 小数 vs u32/定点数、MCP onboarding playbook/repair hints、schema 生成链路、SDK 示例与 local validation/dry-run 缺失。

**处置**: 高优先 Phase 2。Market/IDL/schema 已升级进 B3；AI learnability 记录为 API/DX High。

### CX5: Economy 目标方向补漏队列

**来源**: API/DX、Determinism、Designer、Security → 目标方向: Economy

**发现**: Recycle immediate refund、repair→Recycle 套利、Alliance transfer 绕过、PvE event seed 与 Resource Boom faucet、战斗结算中的 Drain/Fabricate/Depot 掉落资源 ledger。

**处置**: 高优先 Phase 2。升级进 B6。

### CX6: Performance / Infra 目标方向补漏队列

**来源**: Security、Economy、Architect → 目标方向: Performance/Infra

**发现**: `swarm_simulate` 独立 worker pool、大帝国 EconomySnapshot 缓存、WASM 静态分析/编译队列、horizontal sharding 时程。

**处置**: Medium/High。与 B2/B4 部分重叠，其余记录为扩展性条件。

## 方向专属 High 优先级

### A-H1: ECS authoritative chain 与系统读写矩阵不完整

Architect 双模型均指出系统顺序、缺失系统、并行安全与 failure matrix 需要统一。除已升级的 B1/B4 外，还需补完整 20+ system chain、status/aging/regeneration/decay 位置、RoomCap enforcement 与 process crash 语义。

### S-H1: 安全 hardening 项需从建议变为 server-side contract

Security 方向除 B5 外，还要求 CRL cache 默认缩短或强约束、prompt-injection delimiter/server enforcement、`swarm_get_replay` rate limit、CSR/global DoS budget、Origin/Agent transport wording 与 audit redaction。

### D-H1: First-hour / AI learnability / community propagation 仍需产品合同

Designer GPT 给出首小时、AI 学习闭环、replay 分享、bot profile/fork graph 等 High/Medium。Designer DeepSeek 给出 Arena identity conflict、damage resistance coverage、logistics 默认过宽。它们不构成引擎根本否决，但影响 MVP 可玩性与传播。

### P-H1: 扩展性目标与当前预算缺少硬 baseline

Performance 双模型认可方向，但指出 EXECUTE 最坏命令量、path_find 全局上限、Bevy deep copy、visibility filtering、1000-worker RAM、FDB serial transaction 均未达到可实施 baseline。需冻结单节点硬件目标、tick p99、事务大小、worker oversubscription 与 sharding 入场条件。

### E-H1: Vanilla economy 需要数值闭环，不只是机制框架

Economy 双模型要求以数值表和模拟目标验证 upkeep、tax、faucet、transfer、recycle、storage。当前默认参数和边界条件不能证明长期 World 不通胀、不套利、不联盟滚雪球。

### X-H1: Schema-first API gate 是实现前置条件

API/DX 双模型均认为 SDK、IDL、MCP、Host Function、Rhai API 不可继续靠手写表格同步。需要 schema-first 或 IDL-first gate，且必须生成 TS/Rust SDK 最小 bot 示例并通过验证。

### T-H1: Replay determinism 必须先于 gameplay expansion 冻结

Determinism 双模型认为排序键、RNG、ECS、TickTrace、f64/SIMD 是 replay 的硬前置。特殊攻击、经济、RuleMod、NPC 等新增机制必须在同一 Action Manifest/validation/replay verifier 下扩展。

## Medium/Low 处置

| ID | 问题 | 来源方向 | 处置 |
|----|------|---------|------|
| ML1 | Move 作为 main action slot 的新手误解 | Architect GPT / Designer | 纳入 tutorial、SDK lint、first-hour contract |
| ML2 | Snapshot truncation 的玩家可解释性 | Architect GPT / Performance GPT | 与 B7 合并，补 UI/debug wording |
| ML3 | Rhai API 文档不足 | API/DX GPT / Architect GPT | 与 B3 合并，作为 schema gate 子项 |
| ML4 | Replay/highlight/community profile 的 UGC 风险 | Designer GPT / Security CrossCheck | Phase 2 Security + Product backlog |
| ML5 | Delta chain 完整性与 Broadcast 预算 | Performance DeepSeek/GPT | 与 B4 部分合并，剩余进 infra backlog |
| ML6 | Same-origin quota 绕过成本过低 | Economy DeepSeek / Security | 作为 B6/B5 边界条件，补 PoW/abuse model |
| ML7 | Controller repair / age / recycle 边界 | Economy DeepSeek / Determinism DeepSeek | 作为 B6 子项验证结算顺序 |
| ML8 | Damage resistance coverage sparse | Designer DeepSeek | Design High，若留给 mods 需显式声明 vanilla baseline |
| ML9 | CRL fallback `allow_with_warning` scope | Security DeepSeek | 安全 Medium，定义低风险世界标准 |
| ML10 | path_find cache / tie-breaker / node cap | Architect/Security/Determinism | 与 B1/B7 合并，补 deterministic A* contract |

## D-items（需用户裁决）

### D1: Sandbox 生命周期选择

**问题**: 文档同时依赖 long-lived worker pool 的性能与 fork-per-tick 的隔离，二者不可同时作为权威实现。

**选项**:
- A: long-lived worker pool，配合强 reset、cgroup、seccomp、module instance hygiene、trap cleanup。
- B: fork-per-tick / fork-per-run，隔离更强但冷启动与内存成本显著更高。

**推荐**: A。理由：Performance 已证明 B 难以支撑 500/1000 active players；可用安全 hardening 与严格 lifecycle reset 补足隔离，但必须删除 fork-per-tick 默认叙述。

### D2: Command ordering 选择公平 shuffle 还是 canonical order

**问题**: Determinism 双模型指出 seeded shuffle 与字典序 canonical order 同时存在，会导致不同实现产生不同状态。

**选项**:
- A: seeded shuffle 作为执行顺序，TickTrace 记录 seed/epoch/hash 与 shuffle 后 command order。
- B: canonical lexicographic order，牺牲同 tick 公平随机性，换取更简单 replay。

**推荐**: A。理由：当前设计多处强调公平与抗固定排序，保留 seeded shuffle 更符合 MMO 冲突结算；但必须使用无偏 shuffle、明确 hash 输入和 seed 泄露策略。

### D3: Market 是否进入当前冻结面

**问题**: Designer/Economy/API 均指出 Market 被描述为 RFC，但 IDL 已暴露 market commands，SDK 会生成死功能或未治理功能。

**选项**:
- A: 从当前 IDL/默认 SDK 删除 Market，仅保留 RFC 文档。
- B: 将 Market 提升为冻结功能，补 validator、ledger、tax、abuse prevention、visibility policy。

**推荐**: A。理由：当前经济与 ledger 尚未闭合，提前冻结 Market 会扩大 B3/B6 风险。

### D4: Vanilla logistics 默认强度

**问题**: Designer DeepSeek 认为 Mode B 1%/5% 过宽，Economy GPT/DeepSeek 又指出全局↔本地可能三重惩罚。当前默认既可能太轻也可能在组合税下太重，缺少数值目标。

**选项**:
- A: 维持 Mode B，但用 balance sheet 调整税/转换损耗到目标区间。
- B: 默认更硬核，强制本地/运输形成核心玩法。

**推荐**: A。理由：MVP 需要可上手；先用数值表证明 Mode B 能产生但不压垮物流选择，再把硬核模式作为 world.toml profile。

### D5: WASM SIMD 与 f64 策略

**问题**: Determinism DeepSeek 指出 f64 禁用与 WASM SIMD 启用冲突；Performance/Security CrossCheck 还指出 SIMD fuel 计费可能不公平。

**选项**:
- A: P0 禁用 SIMD，减少确定性和 fuel 计费风险。
- B: 允许 SIMD，但 wasmparser 预校验禁止 f64 SIMD opcode，并校准 fuel metering。

**推荐**: A。理由：P0 目标是 deterministic replay 与实现收敛；SIMD 可作为后续性能优化 gated feature。

## 文档维护项

- 建立 R14 Contract Consolidation Checklist，逐项映射 B1-B7 到权威文档与删除/迁移位置。
- 在 reviews index 中记录 R14 verdict：REQUEST_MAJOR_CHANGES，Phase 1 14/14 complete，Phase 2 pending。
- 更新 ROADMAP：冻结前新增“Contract consolidation gate”，包括 Determinism、Sandbox、Schema/API、FDB/TickTrace、Security/Auth、Economy Ledger、Visibility Query 七项。
- 清理过期/冲突段落：fork-per-tick vs worker pool、Market RFC vs IDL、localStorage vs HttpOnly、Move 4-way vs 8-way、host function limits 50 vs 5、排序键 shuffle vs lexicographic。
- 建议下一轮 R15/R14.1 只在上述合同修订后启动；否则评审会重复命中同类问题。

## 评审统计

| Direction | GPT-5.5 Verdict | DeepSeek V4 Pro Verdict | 最高严重度 | 共识强度 |
|-----------|-----------------|--------------------------|------------|----------|
| Architect | REQUEST_MAJOR_CHANGES | REQUEST_MAJOR_CHANGES | Critical | 强：双模型均阻塞 |
| Security | REQUEST_MAJOR_CHANGES | CONDITIONAL_APPROVE | Critical/High | 中强：凭据/限流/sandbox 收敛一致 |
| Designer | CONDITIONAL_APPROVE | CONDITIONAL_APPROVE | Critical/High | 中：玩法可修，非根本否决 |
| Performance | CONDITIONAL_APPROVE | CONDITIONAL_APPROVE | Critical/High | 强：sandbox/FDB/scale 反复命中 |
| Economy | CONDITIONAL_APPROVE | CONDITIONAL_APPROVE | Critical/High | 强：默认参数与 ledger 需闭合 |
| API/DX | REQUEST_MAJOR_CHANGES | CONDITIONAL_APPROVE | Critical | 强：schema/IDL 不可生成 |
| Determinism | REQUEST_MAJOR_CHANGES | REQUEST_MAJOR_CHANGES | Critical | 极强：replay 合同阻塞 |

### Verdict 计数

- REQUEST_MAJOR_CHANGES: 6/14（Architect 2、Determinism 2、Security GPT、API/DX GPT）
- CONDITIONAL_APPROVE: 8/14（Security DeepSeek、Designer 2、Performance 2、Economy 2、API/DX DeepSeek）
- APPROVE: 0/14
- REJECT: 0/14

### 共识强度评估

- 极强共识：Determinism ordering/RNG/ECS/TickTrace 必须先冻结。
- 强共识：Sandbox lifecycle、Command/API schema、FDB/TickTrace failure、Economy ledger/upkeep、Visibility/query oracle 均为跨方向问题。
- 中等共识：First-hour retention、community propagation、damage resistance、logistics 默认强度等属于设计质量提升项，重要但不应遮蔽核心合同阻塞。
- 分歧性质：本轮几乎没有“方向互斥”的价值分歧；主要是多个文档版本并存导致的实现分叉。因此下一步不是辩论取舍，而是做权威合同收敛与删除过期叙述。

## Speaker 结论

R14 证明 Swarm 的设计方向仍然成立：WASM-first、公平 fuel、deferred command、MCP 作为管理/观察界面、Rhai world rules、World/Arena 双模式、资源账本与反雪球思路都被多方向认可。但当前文档尚未达到 Freeze 或 implementation-ready 状态。

进入下一阶段前，必须先完成 B1-B7 的合同收敛；其中 B1/B2/B3/B4 是实现前置硬门，B5/B6/B7 是安全、经济与可见性正确性的冻结门。完成后再启动下一轮 clean-slate 评审，预期多数 REQUEST_MAJOR_CHANGES 可降级为 CONDITIONAL_APPROVE 或 APPROVE。

---

## D-items 裁决结果（2026-06-18 用户裁决）

### D1: Sandbox 生命周期 → ✅ **A（long-lived worker pool）**

采用 long-lived worker pool + 强 reset/cgroup/seccomp 方案。删除 fork-per-tick 默认叙述。安全 hardening（严格 lifecycle reset、trap cleanup）补足隔离。后续文档以 worker pool 为唯一权威模型。

### D2: Command Ordering → ✅ **A（seeded shuffle）**

采用 seeded shuffle 作为执行顺序，分层排序键：`(priority_class, shuffle_index, sequence, source)`。Admin > NPC > Player，Player 类内 Fisher-Yates shuffle，TickTrace 记录 seed epoch + 活跃玩家集合快照。删除 §9.1 的 `(player_id, sequence, source)` 字典序和 validation §2.1 的混合写法。

### D3: Market → ✅ **A（从 IDL 移除，保留 RFC）+ 弱化为游戏内行为**

Market order book 命令从 IDL/默认 SDK 删除，RFC 文档保留。未来 Market 方向从"独立交易所"变为"Transfer + Alliance 的上层抽象"——与 Swarm"一切皆行为"哲学一致。依赖：经济账本闭合（B6）+ Alliance 治理（B5）。

### D4: Vanilla Logistics 默认强度 → ✅ **A（维持 Mode B）**

维持 1%/5% 默认，物流强度为 `world.toml` config knob（非架构决策）。Vanilla Economy Balance Sheet 中纳入物流模拟行进行数值验证。硬核模式作为可选的 world profile。

### D5: WASM SIMD / f64 → ✅ **双模：World 启用 / Arena 禁止**

`world.toml` 新增 `wasm.simd_enabled: bool`：World 模式默认 true（性能优先），Arena 模式默认 false（确定性/公平优先）。f64 类型和 f64 SIMD opcode 全局禁止（确定性合同，不随模式切换）。SIMD 启用时需 wasmparser 预校验 + 校准 fuel metering。
