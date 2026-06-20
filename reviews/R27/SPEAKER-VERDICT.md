# Swarm 设计评审 R27 — Speaker 共识报告

## 裁决概要

- 本轮基于 `/data/swarm/docs/reviews/R27/` 中全部 10 份可用评审报告综合，未读取 `/data/swarm/` 下代码仓库或设计正文，未补跑缺失 reviewer。
- 本轮不是标准 14/14 完整议会，而是 10/10 可用报告：Architect 2/2、Security 2/2、Design/Economy 2/2、API/DX 2/2、Determinism/Performance 2/2；缺少独立 Designer、Performance、Economy、Determinism 四个拆分方向报告。
- 共识信号显示：核心架构方向被多数 reviewer 认可，但多个“文档即合同”的关键边界仍冲突，足以阻断实现冻结；尤其是 Phase 2b 调度、API/IDL/codegen、WASM sandbox 参数、容量/timeout 模型、deploy/auth 控制面。
- Freeze 状态：不可冻结。建议先进行 R27 contract cleanup，再进入下一轮 closure verification 或 narrow clean-slate 验证。
- Phase 1 完成情况：10/10 可用 reviewers；按任务要求统计为 10 reviewer × verdict 矩阵。
- Phase 2 补漏情况：未发现独立 Phase 2 补充报告；本节只汇总 Phase 1 CrossCheck 中被多个方向指向的问题。

## 总体 Verdict

REQUEST_MAJOR_CHANGES

理由：10 份可用报告中 2 份给出 `REQUEST_MAJOR_CHANGES`（GPT Design/Economy、DSV4 API/DX），其余 8 份均为 `CONDITIONAL_APPROVE`。没有 reviewer 判定核心方向失败，但至少 5 类跨方向、跨模型问题满足共识 Blocker 条件，且会直接影响实现者对权威合同、SDK codegen、安全控制面、确定性 replay 与容量承诺的理解。当前应进入集中修正文档合同，而非冻结进入实现。

## 共识 Blocker（跨方向 + 跨模型同意）

### B1: Phase 2b / status_advance 调度权威冲突

**方向 × 模型矩阵**:

- Architect × GPT: A3 指出 `06-phase2b-system-manifest.md` 与 `02-command-validation.md` 的 special attack/status 调度冲突。
- Architect × DeepSeek: C1 指出 `02-command-validation.md §3.19` 是旧调度链，和 manifest 权威链冲突，Critical。
- Determinism/Performance × GPT: T1 指出该冲突会导致 replay 分叉，High。
- Determinism/Performance × DeepSeek: T3/CX2 指出 `status_advance_system` 位置跨文档冲突。

**问题**: `06-phase2b-system-manifest.md` 声明自己是系统调度唯一权威，但 `02-command-validation.md §3.19` 仍保留旧顺序：regeneration、combat、status_advance、decay 的相对位置与 manifest 不一致。实现者若按不同文件编码，会得到不同状态效果、回复、damage application 和 duration decrement 结果，破坏确定性 replay。

**修正要求**:

1. 删除 `02-command-validation.md §3.19` 中完整调度链，改为引用 `06-phase2b-system-manifest.md` 的 Sxx 权威顺序。
2. 若需要说明特殊攻击校验，只描述命令 validation，不重列执行 schedule。
3. 在 doc-lint 中禁止除 manifest 外的完整 Phase 2b 顺序表；其他文档只能引用 manifest。
4. 明确 S16-S21 是否写 `StatusState`：若 S22 是唯一 writer，则前者必须改为 intent/reducer/no-write 描述。

### B2: API/IDL/codegen 单事实源失效，阻断 SDK 生成可信度

**方向 × 模型矩阵**:

- API/DX × GPT: X1 指出 `codegen.md` 的 CommandAction/RejectionReason 计数和 IDL 映射与 Registry 不一致。
- API/DX × DeepSeek: D1-D5 给出 Critical/High：`object_id` 缺失、RejectionReason 79 vs 47、CommandAction 19 vs 21、codegen.md 手写但声明自动生成。
- Architect × GPT: A4 指出 RejectionReason registry 与校验矩阵漂移，旧码污染 SDK 风险。
- Security × GPT: H1/H2/CX3 指出 API Registry 的 Auth/Deploy schema 与安全合同不一致。

**问题**: API Registry 声称 IDL 是机器可读权威源，但派生/说明文档自身保留过期计数、过期 schema、旧 RejectionReason、缺失 `object_id`、错误 section mapping。该问题会直接导致 TypeScript/Rust SDK、MCP schema、CI `--check` 和客户端错误处理分叉。

**修正要求**:

1. 修正 `api-registry.md` / IDL 中所有 CommandAction 参数声明，确保 21 个 action 都包含共享 `object_id: EntityId`。
2. 将 `codegen.md` 的 CommandAction 数、RejectionReason 数、Auth 输出映射与当前 IDL/Registry 对齐；若无法自动生成，必须标明其为手工维护并加入 CI 校验。
3. 清理 `02-command-validation.md` 等非权威文档中的非 canonical RejectionReason：改为 `canonical_code` + `debug_detail.example` 两列。
4. 明确唯一 codegen 路径：`hermes codegen generate`、Python script、IDL → Registry → SDK 之间必须只有一个权威入口或清晰 wrapper 关系。
5. 执行并记录 codegen `--check` / doc count 校验结果，作为 R28 入口条件。

### B3: WASM sandbox / host ABI 资源与错误合同冲突

**方向 × 模型矩阵**:

- Architect × DeepSeek: H2/H3 指出 seccomp `clone` 策略和 `pids.max` 双值冲突。
- Security × GPT: M1 指出 seccomp、namespace、pids cap 矛盾会使沙箱实现落空。
- Security × DeepSeek: M2 指出 `pids.max = 32` vs `16`，建议统一。
- API/DX × GPT: X3 指出 host function 成功返回值语义 bytes_written vs 0 不一致。
- API/DX × DeepSeek: D4/D16 指出 `host_get_objects_in_range` `i32/u32` 类型冲突与 budget error code `-1` 冲突。

**问题**: WASM sandbox 的 OS 加固表、cgroup 参数、host function ABI、错误码优先级在不同文档间冲突。实现阶段这些合同通常由不同模块/脚本落地，一旦不统一，会产生“开发能跑、生产被 seccomp/cgroup 打断”或 SDK wrapper 错读 buffer/error 的问题。

**修正要求**:

1. 以一个 sandbox hardening checklist 为唯一权威，统一 `clone` 策略、network namespace、`pids.max`、`cpu.max`。
2. 明确 Wasmtime 30.x 实际线程/syscall 需求；若允许有限 `clone`，不得在总表写“全禁”。
3. 统一 host function ABI：推荐 `ret >= 0` 为 `bytes_written`，`ret < 0` 为错误码；或补充 out_len 机制后统一为 `0 = success`。
4. 统一 `host_get_objects_in_range(range)` 类型，推荐以 IDL `u32` 为准。
5. 修正 budget 错误码：budget exhaustion 不得返回 `-1 ERR_MEMORY_BOUNDS`，应使用 canonical `ERR_BUDGET_EXHAUSTED` / `ERR_PLAYER_BUDGET`。

### B4: 500/1000 玩家容量承诺与 worker pool / timeout / CPU budget 模型不闭合

**方向 × 模型矩阵**:

- Determinism/Performance × GPT: P1/P2/P5 指出 1000 worker、snapshot stitching、commit budget 等容量推导过度乐观。
- Determinism/Performance × DeepSeek: P1/P2 Critical 指出 500 players COLLECT budget 零余量、worker pool 与 per-player timeout 冲突。
- Architect × GPT: A5/A6 指出 500/1000 容量与单事务/partition phase gate、Bevy rollback benchmark 不对齐。
- Architect × DeepSeek: Algorithmic Risks 指出 500/1000 snapshot、sort、room partition 2PC 需 benchmark。
- Security × GPT: M2/CX2 指出 simulate/dry-run 预算与最坏情况 CPU 成本不一致。

**问题**: 文档同时给出 target 500 / hard cap 1000 active players、worker pool 默认 256、per-player deadline 2500ms、每 sandbox 固定 cgroup quota、single-tx / room-partition / 500ms commit gate 等多个口径。当前模型在 500 players 已接近或达到饱和，在 1000 players 更像 stress aspiration，而非可冻结合同。

**修正要求**:

1. 将 1000 active players 明确标为 benchmark-gated hard cap + operator override，不作为默认承诺。
2. 将 500 players 标为 target/stress target 前，必须给出 aggregate CPU admission 公式、worker pool 排队语义和 p99/p999 benchmark gate。
3. 修正 worker pool 与 per-player timeout 冲突：选择独占 worker、按 worker 分片 timeout、或改成可抢占/async dispatch 模型。
4. 区分 MVP single-tx、World room-partition、Arena commit budgets；不得同时把 50ms p99 与 500ms p99 作为同一生产 SLO。
5. 统一 Bevy snapshot/restore benchmark 与 50k entity 容量目标，并将 entity allocator、pending queues、ledger buffers 纳入 restore 必捕获清单。

### B5: Deploy/Auth 安全控制面与 Registry schema 不一致

**方向 × 模型矩阵**:

- Security × GPT: H1/H2/H4 指出旧式 cert issue API、deploy replay schema、WebSocket per-message MAC 冲突。
- Security × DeepSeek: H1/H2/H3 指出 CodeSigningCertificate TTL、refresh grace、CRL 默认延迟问题。
- API/DX × DeepSeek: D14/D15 指出 deploy validation_errors 未类型化、版本兼容策略缺失。
- API/DX × GPT: X2/X7 指出 JSON-RPC error envelope 与 Auth 工具重复 schema 影响 SDK/安全语义。
- Architect × GPT: A2/CX5 指出 TickTrace/deploy/replay-critical 术语和 Registry 生成链仍需权威化。

**问题**: Auth/Deploy/WS 属于安全关键控制面，但设计文档、security spec、API Registry 对证书签发、deploy payload 签名、version counter、per-message MAC、CRL fresh check、工具 schema 的表达不一致。实现者若以 Registry 为准，可能落地泛化证书签发、无 code-signing payload 的 deploy、或“握手后免签”的 WS。

**修正要求**:

1. 移除或重命名通用 `swarm_auth_cert_issue/rotate/list/revoke` 控制面；保留时必须绑定 CSR/proof、usage/scope/audience、dual approval，并禁止 TLS-style SAN 任意签发。
2. 统一 deploy replay 模型：推荐客户端签名 payload 含 `expected_previous_counter` 或 `idempotency_key`，服务端 FDB CAS 递增最终 `version_counter`，manifest 写入最终 counter。
3. `swarm_deploy` input schema 必须包含 code-signing certificate、deploy payload/signature、module_hash、metadata_hash、module_slot、world_id、idempotency_key。
4. Agent WS 统一为 handshake + per-message seq/signature/MAC；删除“后续消息免签名”的歧义描述。
5. 对 deploy/admin/recovery 强制 CRL fresh check 或极短 TTL；CRL 默认按 World/Arena/competitive 模式分级。

## CrossCheck 补漏发现（基于 Phase 2）

未发现独立 Phase 2 补充报告；以下为 Phase 1 CrossCheck 中被多个方向重复指向的补漏主题，处置为纳入上方 Blocker 或 Medium/High 跟踪。

### CX1: Wasmtime syscall / cgroup 策略

**来源**: Architect GPT/DSV4 → Security；Security GPT/DSV4 已独立确认。
**发现**: `clone`、network namespace、`pids.max` 多处冲突。
**处置**: 升级为 B3。

### CX2: simulate/dry_run 预算与隔离

**来源**: Security GPT、API/DX GPT、API/DX DSV4、Determinism/Performance GPT。
**发现**: simulate/dry-run 输入模型、rate limit、fuel/hour、fork 隔离、RNG seed 与成本预算不一致。
**处置**: 记录为 Medium；预算/容量部分并入 B4，API 输入模型并入 X-H/M 项。

### CX3: Rhai mod API 合同缺失

**来源**: API/DX GPT/DSV4 → Architect/Security。
**发现**: tech choice 已选择 Rhai，但 hook、helper、capability、错误/回滚语义、版本策略缺失。
**处置**: 记录为 API/DX High-to-Medium；未达共识 Blocker，但需在实现 mod 系统前补齐。

### CX4: RNG seed disclosure / forward secrecy

**来源**: Determinism/Performance GPT/DSV4 → Security/Architect；Architect GPT 也提出 world_seed 轮换公平性。
**发现**: 赛中不可预测与 replay 可验证之间缺少 seed disclosure boundary / commit-reveal / 异常检测 spec。
**处置**: 记录为 T-H1；若无 seed-leak detection spec，应在后续升级为 Blocker。

### CX5: Allied Transfer / logistics / economy 语义漂移

**来源**: Design/Economy GPT/DSV4 → API/DX/Architect/Security。
**发现**: allied transfer 是否直接/延迟/禁用、运输中可拦截规则、资源 ownership 与并发原子性不闭合。
**处置**: 记录为 E-H/D-H；未达跨技术方向共识 Blocker，但必须在玩法经济冻结前处理。

## 方向专属 High 优先级

### A-H1: 权威源路径与链接漂移

来源：Architect GPT A1。多个相对链接从新 docs layout 拆分后路径错误，可能让读者和 CI link-check 打开错误文件。处置：加入 doc link-check gate，统一 docs-root 或相对路径规则。

### A-H2: TickTrace / replay-critical / rich trace blob 术语混用

来源：Architect GPT A2，Security DSV4 CX3。`TickTrace`、FDB replay-critical subset、object store blob、delta chain/keyframe 表述仍混用。处置：建立 glossary，区分 `TickCommitRecord`、`RichTraceBlob`、`ReplayArtifact`。

### S-H1: CSR/PoW 注册路径缺少服务端硬 admission control

来源：Security GPT H3。PoW 不能替代 per-IP/per-ASN/global queue/CSR signing worker pool。处置：为 `swarm_submit_csr` 增加服务端限流、签发 semaphore、排队超时和审计限速。

### S-H2: Refresh token grace 与 family revoke DoS

来源：Security DSV4 H2。60s grace 可能被盗 token 重放触发持续 session family revoke。处置：FDB 事务原子消费，同 IP/UA/client key 绑定，family revoke 频率上限。

### D-H1: 早期经济闭环与 first-hour 承诺冲突

来源：Design/Economy GPT G1/E1，DSV4 G2/G3。Standard balance sheet 展示 1/5/20/50 房全为负，而 resource-ledger 声称 tick 2000+ 自维持；drone upkeep 在表中建模不一致。处置：新增 tick 0/500/1500/2000/5000/10000 目标曲线，提供 2-room/5-drone 正/平衡参考配置，统一所有平衡表的 drone upkeep。

### D-H2: Onboarding / AI agent 宏目标 API 缺失

来源：Design/Economy GPT G3，API/DX GPT X5。工具存在但缺少机器可读“下一步做什么”的目标合同。处置：新增 `swarm_get_objectives` 或等效 tutorial resource，配套 starter-bot MCP-only smoke test。

### D-H3: 特殊攻击 MVP 面过宽且部分状态机未定义

来源：Design/Economy GPT G5，DSV4 G5/G7/G8。Standard 启用 8 种 special attack 造成学习 cliff；Hack neutral window、Overload 多攻击者压制、Hack cost/成功率公式不完整。处置：MVP 缩到 2-4 个 special，定义 Neutral/Hack/Overload 完整交互和反制。

### P-H1: COLLECT budget / worker pool 模型阻塞 500-player 验证

来源：Determinism/Performance DSV4 P1/P2 Critical，GPT P1。处置：归入 B4，作为性能方向最高优先级。

### P-H2: snapshot stitching / FDB room partition / Phase 2a serial loop benchmark 风险

来源：Determinism/Performance GPT P2/P4/P5，DSV4 P3/P5/P6。处置：新增 pre-serialized room chunks、Phase 2a deterministic partitioner 路线、明确 room-partition p99 SLO。

### E-H1: Allied Transfer 与物流拦截规则不闭合

来源：Design/Economy GPT E4，DSV4 G1。处置：选择 Standard 规则（建议 restricted delayed transfer with caps），定义 in-transit ownership、intercept condition/result、cartel abuse 分析。

### E-H2: Storage tax 与 PvE faucet 缺少真实时间/阶段化量化

来源：Design/Economy GPT E2/E3，DSV4 G4。处置：把 bp/tick 转成 per-hour/per-day，说明 PvE 收益定位（catch-up/skill test/risk reward）和阶段收入表。

### X-H1: JSON-RPC error envelope 双轨

来源：API/DX GPT X2。`error.code` numeric vs string 冲突。处置：推荐保留 JSON-RPC numeric code，canonical enum 放入 `error.data.swarm_error` / `data.rejection_reason`。

### X-H2: Host function ABI 与 MCP tool 表面不清

来源：API/DX GPT X3，DSV4 D4/D11/D16。处置：归入 B3；另需明确 `swarm_get_terrain` / `swarm_get_path` 是 MCP 工具还是 host-only。

### T-H1: RNG seed disclosure boundary 与 forward secrecy 风险

来源：Determinism/Performance GPT T2，DSV4 T1。处置：定义 seed_epoch 为 opaque id，赛中不可见；如需公开 replay，用 delayed commit-reveal 或 admin/offline authority 提供 seed material；补 seed-leak detection spec。

### T-H2: Room-partition cross-room 2PC fallback 与 deterministic replay 冲突

来源：Determinism/Performance GPT T3，Architect DSV4 Algorithmic Risks。处置：删除 “best-effort mutate” 语义；跨 room 操作必须 all-prepare-success commit，否则 deterministic abort/retry，并将 attempt_id/conflict set/participant order 纳入 replay-critical subset。

## Medium/Low 处置

| ID | 问题 | 来源方向 | 处置 |
|----|------|---------|------|
| ML-1 | Command validation output 256KB vs 1MB | Determinism/Performance GPT | 统一 WASM tick output hard cap 256KB；若 1MB 是 MCP/Admin batch，另命名。 |
| ML-2 | canonical serialization / command_hash 仍不够机器化 | Determinism/Performance GPT | 定义 canonical codec，`command_hash` hash canonical RawCommand 而非原始 JSON。 |
| ML-3 | ECS entity iteration CI 无法检测遗漏排序 | Determinism/Performance DSV4 | 增加 randomized entity iteration order test。 |
| ML-4 | `host_path_find cache_miss_penalty` 未量化 | Security DSV4、Determinism/Performance DSV4 | 设固定 fuel 值，避免硬件相关成本影响确定性。 |
| ML-5 | Dragonfly update 阻塞 NATS broadcast | Determinism/Performance DSV4 | Dragonfly update 与 NATS publish 并行或异步化。 |
| ML-6 | world tiers / modded variability 缺少产品 taxonomy | Design/Economy GPT | 定义 Tutorial/Novice/Standard/Advanced/Modded 矩阵。 |
| ML-7 | replay privacy 与 code disclosure 策略不完整 | Design/Economy GPT、Security CX | 默认 replay without source，source map/code line provenance 需 opt-in。 |
| ML-8 | MCP tool optional/default/error catalog 不完整 | API/DX DSV4 | IDL 为每个字段标 required/optional/default，并列 per-tool errors。 |
| ML-9 | Auth API duplicate shortcut schema | API/DX GPT | 标注 `alias_of` / `schema_source=auth_api`，SDK 不生成重复函数。 |
| ML-10 | CRL federation stale 时仍允许 login | Security DSV4 | 默认策略从 `reject_for_code` 升级为 `reject_for_code_and_login` 或说明风险。 |
| ML-11 | player_id 64-bit hash 与 full identity key | Security GPT | Auth/FDB/audit 保留 256-bit identity fingerprint，u64 仅游戏内短 ID。 |
| ML-12 | `InsufficientResources` 残留 | API/DX DSV4 | grep 清理为 canonical `InsufficientResource`。 |

## D-items（需用户裁决）

### D1: JSON-RPC error envelope 采用 numeric 还是 string code

**问题**: `design/interface.md` 使用 JSON-RPC numeric `error.code = -32000` + `data.swarm_error`，`api-registry.md` 使用 string `error.code = "RejectionReason"`。两者互斥。

**选项**:

- A: 保留标准 JSON-RPC numeric `error.code`，Swarm canonical enum 放在 `error.data.rejection_reason` / `error.data.swarm_error`。
- B: 使用 string `error.code` 作为 Swarm enum，并明确这是非标准 JSON-RPC envelope，SDK 自行适配。

**推荐**: A。理由：兼容 JSON-RPC/MCP 客户端库，安全 detail 可以集中放入 `data` 分层，SDK typed exception 仍可从 canonical enum 生成。

### D2: Host function ABI 成功返回语义

**问题**: 文档同时出现 `0=成功` 与 `返回 bytes_written` 两种模型。

**选项**:

- A: `ret >= 0` 表示 `bytes_written`，`ret < 0` 表示 canonical ABI error code。
- B: `ret == 0` 表示成功，实际长度通过 out_len 指针或 buffer header 返回。

**推荐**: A。理由：ABI 简单，适合 C/Rust/TS wrapper，避免额外 out pointer；只需确保 0 bytes 是合法空结果。

### D3: 500-player 容量声明的产品口径

**问题**: 当前 COLLECT budget 与 worker pool 模型表明 500 active players 不是安全余量点，1000 更是 benchmark-gated aspiration。

**选项**:

- A: 文档降级为 safe target 350-400，500 为 stress target，1000 为 operator override hard cap。
- B: 保留 target 500，但必须同步引入更强 worker/async/zero-copy 设计并把 benchmark gate 作为冻结前条件。

**推荐**: A。理由：不夸大承诺；允许实现先稳定交付，再用 benchmark 提升公开容量。

### D4: Standard 世界早期经济目标

**问题**: Standard balance sheet 全负，与 first-hour/self-sustain 承诺冲突。

**选项**:

- A: 将 Novice 作为默认 onboarding world，Standard 明确为 seasoned/deflationary world，早期经济正闭环只要求 Novice。
- B: 调整 Standard 参数，使 starter path 在 tick 2000 前达到非负 net flow。

**推荐**: A。理由：保留 Standard 的反雪球压力，同时不让新手第一世界进入负反馈；符合 Design/Economy GPT 的“Treat Standard as Seasoned World; make Novice default”。

### D5: Special attacks MVP 冻结范围

**问题**: Standard 启用 8 个 special attack，学习曲线和状态机表面过大。

**选项**:

- A: MVP/Standard 初始只启用 2-4 个 special（Disrupt、Fortify、Drain、可选 Overload），Leech/Fabricate 等转入 expansion/RFC。
- B: 保留 8 个，但必须为每个补完整 state machine、unlock/tutorial、counterplay 和 SDK manifest。

**推荐**: A。理由：降低冻结面和教学负担，把高风险状态转换留到后续 telemetry 驱动。

### D6: Cross-room fallback 策略

**问题**: room-partition 跨房间 2PC 超时后 "best-effort fallback" 与 deterministic replay 原子性冲突。

**选项**:

- A: 禁止半边 best-effort mutate；任一失败 → deterministic abort/retry，或 tick/room-pair locked。
- B: 保留 best-effort，但设计补偿命令、terminal state 和 replay-critical 记录。

**推荐**: A。理由：简单、可验证、符合确定性游戏引擎的原子闭包；B 的补偿系统复杂度过高。

**裁决**: ✅ A — deterministic abort/retry，禁止 best-effort mutate。

## D-items 裁决结果（2026-06-20）

| D# | 问题 | 裁决 | 方向 |
|----|------|------|------|
| D1 | JSON-RPC error.code | A — numeric code + data.rejection_reason | 全局统一为 JSON-RPC numeric error.code |
| D2 | Host function ABI 成功语义 | A — ret >= 0 = bytes_written, ret < 0 = error | 统一 host function ABI 合同 |
| D3 | 500-player 容量声明 | **保持当前** — 不降级不强化，benchmark-gated | 允许 tick 时间换取容量，实际限制由压力测试确定 |
| D4 | Standard 世界早期经济 | A — Novice 默认 onboarding / Standard = seasoned deflationary | World/Arena 均适用 |
| D5 | Special attacks MVP 范围 | **保留全部 8 个** — 作为目标设计，补齐未完整状态机 | 无 MVP/Phase 概念，设计即目标 |
| D6 | Cross-room 2PC fallback | A — deterministic abort/retry，禁止 best-effort | 全局确定性合同 |

## 文档维护项

1. 建立 R27 contract cleanup checklist，按 B1-B5 修复后再发起 R28。
2. 增加 doc-lint：链接校验、非权威完整 schedule 禁止、RejectionReason deprecated grep、MCP/tool count 校验、host fn signature 一致性校验。
3. 建立 glossary：`TickCommitRecord`、`RichTraceBlob`、`ReplayArtifact`、`RawCommand`、`CommandIntent`、`ValidatedCommand`、`DeployPayload`、`fdb_version_counter`、`version_counter`。
4. 明确 review artifacts 与 design contracts 分离：本裁决只记录 R27 评审结果，不应被实现文档引用为当前产品状态。
5. R28 建议采用 Closure Verification 模式，编号验证 B1-B5 + D1-D6 决策落地，而非全量开放式重审。

## 评审统计

### Reviewer verdict 矩阵（10 reviewers）

| Reviewer | 方向 | Verdict | 最高严重度 | 主要信号 |
|----------|------|---------|------------|----------|
| rev-gpt-architect | Architect | CONDITIONAL_APPROVE | High | 路径/权威源、TickTrace 术语、Phase 2b 调度、API registry 漂移、容量 gate |
| rev-dsv4-architect | Architect | CONDITIONAL_APPROVE | Critical | `02` 旧调度链 vs `06` manifest，EXECUTE timeout、seccomp/pids 冲突 |
| rev-gpt-security | Security | CONDITIONAL_APPROVE | High | 旧证书 API、deploy replay、CSR DoS、WS per-message MAC 冲突 |
| rev-dsv4-security | Security | CONDITIONAL_APPROVE | High | CodeSigning TTL、refresh grace DoS、CRL TTL、pids.max、federation CRL |
| rev-gpt-design-economy | Design/Economy | REQUEST_MAJOR_CHANGES | Critical | 早期经济不闭合、first-hour 冲突、Arena loop、special attack 复杂度 |
| rev-dsv4-design-economy | Design/Economy | CONDITIONAL_APPROVE | High | 运输拦截未定义、平衡表全负、drone upkeep 建模不一致 |
| rev-gpt-apidx | API/DX | CONDITIONAL_APPROVE | High | codegen/Registry 漂移、JSON-RPC error、host ABI、quickstart 缺失 |
| rev-dsv4-apidx | API/DX | REQUEST_MAJOR_CHANGES | Critical | `object_id` 缺失、79 vs 47、19 vs 21、host fn type、codegen 自矛盾 |
| rev-gpt-determinism-perf | Determinism/Performance | CONDITIONAL_APPROVE | High | Phase 2b 顺序、RNG seed、2PC fallback、1000 capacity、snapshot/FDB 风险 |
| rev-dsv4-determinism-perf | Determinism/Performance | CONDITIONAL_APPROVE | Critical | COLLECT 零余量、worker pool vs timeout、seed forward secrecy |

### Verdict 分布

| Verdict | 数量 | Reviewers |
|---------|------|-----------|
| APPROVE | 0 | — |
| CONDITIONAL_APPROVE | 8 | Architect×2, Security×2, DSV4 Design/Economy, GPT API/DX, Determinism/Performance×2 |
| REQUEST_MAJOR_CHANGES | 2 | GPT Design/Economy, DSV4 API/DX |
| REJECT | 0 | — |

### 共识强度评估

- B1 Phase 2b 调度冲突：强共识。4 reviewers、2 方向、2 模型直接命中，且 Architect + Determinism 均认为影响实现/replay。
- B2 API/IDL/codegen 漂移：强共识。API/DX 双模型直接命中，Architect/Security 从 RejectionReason/Auth/Deploy 角度交叉确认。
- B3 WASM sandbox / host ABI 冲突：中强共识。Security/Architect/API-DX 三方向均发现不同层面的同一类“运行合同漂移”。
- B4 容量/worker/timeout 模型：强共识。Performance 双模型直接命中，Architect 也要求 capacity phase gate。
- B5 Deploy/Auth 控制面：中强共识。Security 双模型直接命中，API/DX 与 Architect 从 schema/replay 角度补强。
- 早期经济闭环：方向内强共识（Design/Economy 双模型），但缺少第二技术方向直接同意，因此不列入共识 Blocker，列为 D-H1/E-H。

## R28 入场建议

R27 修正后，R28 不建议全量开放式重审；建议 Closure Verification，仅验证：

1. B1 Phase 2b 调度唯一权威是否闭合。
2. B2 IDL/Registry/codegen/object_id/RejectionReason 计数是否闭合。
3. B3 sandbox/host ABI/syscall/pids/error code 是否闭合。
4. B4 500/1000 容量、worker pool、timeout、benchmark gate 口径是否闭合。
5. B5 Auth/Deploy/WS/CRL 控制面是否闭合。
6. D1-D6 用户裁决是否已按选择同步到文档。
