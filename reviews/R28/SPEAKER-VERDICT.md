# Swarm 设计评审 R28 — Speaker Closure Verification 共识报告

## 裁决概要

- 本轮类型：Closure Verification（R5 pattern），窄范围验证 R27 指定闭合项；不执行 Phase 1/Phase 2 两级阅读，不引入开放式新设计评审。
- 完成情况：10/10 reviewer 报告齐全（5 DSV4 + 5 GPT），Speaker 未补跑 reviewer。
- 综合结论：多数核心修复已经落地，但仍存在跨模型确认的安全残留、API/DX 残留、以及 Determinism/Performance 对 B4 的关键分歧。
- Freeze 状态：不建议宣告全部闭合；进入 R29 ultra-narrow CV 前需先修复下列 GAP。

## 总体 Verdict

**PARTIALLY_CLOSED**

原因：B3、B5、T-H1、S-H2、E-H1、ML-1、ML-3、ML-4、ML-7 等项可视为闭合或基本闭合；但 B4、S-H1、ML-10、ML-11、ML-5 以及若干 API/DX 机器可读合同仍未完全闭合。R28 不满足 CLOSED。

## Reviewer Verdict 矩阵

| Reviewer | Verdict | 主要结论 |
|---|---|---|
| rev-architect.md | APPROVE_WITH_RESERVATIONS | 主项闭合；提出 `swarm_get_server_trust` 未注册与 hard cap benchmark-gated 两个 Low GAP |
| rev-security.md | APPROVE_WITH_RESERVATIONS | B3/B5/S-H2/T-H1/E-H1 闭合；ML-10/ML-11 High，S-H1 Medium |
| rev-dsv4-design-economy.md | CONDITIONAL_APPROVE | D-H2/E-H1/ML-6/ML-7 均判闭合，无 GAP |
| rev-dsv4-apidx.md | CONDITIONAL_APPROVE | B2 核心闭合；validation 残留码、D1 YAML、ObjectiveType/API registry 可见性、ML-8 残留 |
| rev-dsv4-determinism-perf.md | CONDITIONAL_APPROVE | T-H1/ML-1/ML-3/ML-4 闭合；B4 partial、ML-2 GAP、ML-5 partial |
| rev-gpt-architect.md | PARTIALLY_CLOSED | B1/B4/B5/A-H2/T-H1 pass；A-H1 broken links 与 CX3 Rhai ABI 未闭合 |
| rev-gpt-security.md | PARTIALLY_CLOSED | B3/B5/S-H2/T-H1 pass；S-H1 fail、ML-10 partial、ML-11 fail |
| rev-gpt-design-economy.md | PARTIALLY_CLOSED | D-H2/E-H1/ML-7 closed；ML-6 Modded tier 缺失 |
| rev-gpt-apidx.md | PARTIALLY_CLOSED | B2/ML-1/ML-2 pass；D-H2/codegen count、ML-8、ML-9 未闭合 |
| rev-gpt-determinism-perf.md | PARTIALLY_CLOSED | B4/T-H1/ML-3 pass；ML-5 fail，ML-4 authority conflict |

## 共识 Blocker / GAP（跨模型或高严重度）

### G1: S-H1 CSR admission control 未闭合

**方向 × 模型矩阵**: Security × DSV4（Medium）、Security × GPT（High FAIL）

**问题**: R27 要求 CSR admission control 补齐 per-IP / ASN / global / semaphore / queue 等保护。R28 文档仍明确声明 CSR submission 不设 IP/username 限速，主要依赖 PoW。

**证据**:
- `rev-security.md:59` 至 `rev-security.md:87`：DSV4 指出 CSR 提交无 per-IP/ASN/global semaphore，建议补轻量限速或威胁模型接受声明。
- `rev-gpt-security.md:18` 至 `rev-gpt-security.md:32`：GPT Security 判定 S-H1 FAIL，指出缺 CSR-specific ASN limit、global in-flight cap、worker semaphore、bounded queue/backpressure。
- `design/auth.md:830` 至 `design/auth.md:836`：CSR submission 行仍为无 per-IP 限制，global protection 为 PoW，并明述 PoW 是速率控制。
- `design/auth.md:915` 至 `design/auth.md:921`：unauth endpoint protection 中再次说明 CSR submission 仅受 PoW 限制、无额外 IP limit。

**修正要求**:
- 选择并写入一种闭合策略：A. CSR per-IP + global/semaphore + bounded queue；或 B. 明确接受 PoW-only，并补分布式 PoW/FDB 写入风暴威胁模型与容量上限。
- 若沿用 PoW-only，必须说明为何 R27 要求的 ASN/global/semaphore/queue 不采纳，并给出可审计的风险接受理由。

### G2: ML-10 CRL stale fallback 默认值/枚举不一致

**方向 × 模型矩阵**: Security × DSV4（High）、Security × GPT（Partial/Medium conflict）

**问题**: 文档中新增了 `reject_for_code_and_login` 升级意图，但正式枚举与默认示例仍使用旧值 `reject_for_code`，造成实现路径分裂。

**证据**:
- `rev-security.md:108` 至 `rev-security.md:147`：DSV4 判定 High，指出 §15.2a/§15.6 枚举缺少 `reject_for_code_and_login`，示例仍为 `reject_for_code`。
- `rev-gpt-security.md:90` 至 `rev-gpt-security.md:100`：GPT Security 判定 Partial，说明推荐语已加但周边默认文本仍冲突。
- `design/auth.md:1289` 至 `design/auth.md:1296`：default policy 示例仍是 `revocation_fallback = "reject_for_code"`，下一行才写升级建议。
- `design/auth.md:1334` 至 `design/auth.md:1340`：`revocation_fallback` 策略表只有 `reject_for_code`、`reject_all`、`allow_with_warning`，无 `reject_for_code_and_login`。

**修正要求**:
- 在所有 `revocation_fallback` 枚举表中加入 `reject_for_code_and_login`。
- 将默认示例改为 `reject_for_code_and_login`，或删除升级建议并明确保留 `reject_for_code` 的安全理由；二者只能选一。

### G3: ML-11 256-bit `identity_fingerprint` 未定义

**方向 × 模型矩阵**: Security × DSV4（High）、Security × GPT（FAIL）

**问题**: R27 要求区分 256-bit stable identity fingerprint 与 64-bit runtime `player_id`。R28 文档仍只定义 `player_id: u64`，未在身份模型或 FDB schema 中定义 `identity_fingerprint`。

**证据**:
- `rev-security.md:150` 至 `rev-security.md:191`：DSV4 指出 `identity_fingerprint` 字段在 auth.md FDB schema 与 identity 模型中均未定义。
- `rev-gpt-security.md:102` 至 `rev-gpt-security.md:114`：GPT Security 未找到 stable 256-bit identity fingerprint 区分，判定 FAIL。
- `design/auth.md:516` 至 `design/auth.md:530`：三层身份只列 `login_username`、`display_name`、`player_id: u64`，并用 Blake3 低 64 bits 推导。

**修正要求**:
- 在身份模型中新增 `identity_fingerprint: [u8; 32]`，定义为完整 Blake3 输出。
- 说明 `player_id: u64` 是 runtime/engine id，`identity_fingerprint` 是审计、联邦、碰撞排查用 stable identity。
- 在 FDB identity record schema 与相关 auth events 中补字段或说明不进入事件的理由。

### G4: B4 worker pool vs per-player timeout 冲突仍有模型分歧，不能 clean close

**方向 × 模型矩阵**: Determinism/Performance × DSV4（Critical/PARTIAL）、GPT（PASS），Architect × GPT（PASS）

**问题**: GPT reviewers 认为 benchmark-gated + timeout 语义足够闭合；DSV4 Determinism/Performance 认为 R27 的核心要求是解决 worker pool 256 与 per-player 2500ms deadline 的排队语义，当前仍未选择独占 worker、per-worker shard timeout 或 async dispatch。

**证据**:
- `rev-dsv4-determinism-perf.md:29` 至 `rev-dsv4-determinism-perf.md:77`：DSV4 明确判 B4 PARTIAL，指出 queued player 可能“从未开始执行”，而不是 timeout。
- `rev-gpt-determinism-perf.md:14` 至 `rev-gpt-determinism-perf.md:30`：GPT 判 B4 PASS，认为 benchmark-gated 与 timeout handling 足够。
- `design/engine.md:337` 至 `design/engine.md:360`：worker pool 仍为 `min(worker_pool_max, active_players)`，默认 256；500 active players 时每 worker 约 2 players，仅写 “graceful queuing, fair-share slot allocation”，未定义 queue deadline。

**Speaker 处置**: 因该项是 R27 Critical/High 来源且 DSV4 给出可复现实例，不能裁为 CLOSED。状态为 **PARTIAL / D-item required**。

**修正要求**:
- 明确 queued player 的 deadline 从 tick start 还是 worker start 计时。
- 若从 tick start 计时，写入 queue 超时玩家本 tick 输出 0 command 与 TickTrace reason。
- 若从 worker start 计时，则需说明 2500ms collect budget 如何仍可覆盖所有 active players；否则与 tick SLO 冲突。

### G5: ML-5 Dragonfly update 与 NATS publish 未并行化

**方向 × 模型矩阵**: Determinism/Performance × DSV4（PARTIAL/Low）、GPT（FAIL）

**问题**: R27 要求 Dragonfly update 与 NATS broadcast 并行或异步。R28 只补了“非权威缓存，允许滞后”语义，但流程仍为 `Dragonfly.update(delta)` 后 `NATS.publish(...)`。

**证据**:
- `rev-dsv4-determinism-perf.md:182` 至 `rev-dsv4-determinism-perf.md:202`：DSV4 判 PARTIAL，指出顺序仍串行。
- `rev-gpt-determinism-perf.md:84` 至 `rev-gpt-determinism-perf.md:97`：GPT 判 FAIL，认为没有表达并行 fan-out。
- `specs/core/01-tick-protocol.md:518` 至 `specs/core/01-tick-protocol.md:526`：流程标题为“持久化 → 缓存 → 发布”，步骤 2/3 顺序为 Dragonfly 再 NATS。

**修正要求**:
- 将 BROADCAST 表述改为 post-commit delta fan-out：Dragonfly.update 与 NATS.publish 独立异步分支；任一失败均不 rollback。
- 或明确接受串行顺序，并把 R27 要求降级为实现期优化；否则不能闭合。

## 方向专属 High / Medium 残留

### A-H1: broken links 与 `swarm_get_server_trust` registry 缺口

- `rev-gpt-architect.md:14` 至 `rev-gpt-architect.md:28`：GPT Architect 指出 20 个 unresolved relative links，尤其 manifest 与 snapshot contract 相对路径。
- `rev-architect.md:36` 至 `rev-architect.md:43`：DSV4 Architect 指出 `swarm_get_server_trust` 在 `design/auth.md` 有定义但未注册到 api-registry/auth_api。
- Speaker 处置：A-H1 link hygiene 若 reviewer 使用的是 `/tmp/swarm/docs` 不完整副本，部分 link 可能是假阳性；但 manifest 相对路径与 `swarm_get_server_trust` registry 缺口应进入 R29 Low/Medium hygiene。

### CX3: Rhai RuleMod ABI 完整性存在分歧

- `rev-architect.md:24` 至 `rev-architect.md:28`：DSV4 Architect 认为 9 hooks、RhaiActionBuffer、fixed-point、single validation path 均闭合。
- `rev-gpt-architect.md:29` 至 `rev-gpt-architect.md:42`：GPT Architect 认为只有边界 note，没有完整 hooks/helpers/capabilities/errors/version ABI。
- Speaker 处置：不升级为 Blocker；记录为 High design-contract residual。若 R27 CX3 的验收标准要求“完整可实现 ABI”，则需补；若只要求“Rhai 不绕过 command validation”，则已闭合。

### D-H2 / ObjectiveType / MCP tool count

- `rev-dsv4-design-economy.md:9` 至 `rev-dsv4-design-economy.md:20` 与 `rev-gpt-design-economy.md:11` 至 `rev-gpt-design-economy.md:27` 均确认 `/data/swarm/docs/specs/reference/game_api.idl.yaml:56` 至 `:67` 存在 `ObjectiveType` 8 variants，D-H2 设计/经济侧 CLOSED。
- `rev-dsv4-apidx.md:79` 至 `rev-dsv4-apidx.md:82` 与 `rev-gpt-apidx.md:33` 至 `rev-gpt-apidx.md:45` 指出 API Registry/required-file view 中 enum 不可见，且 `codegen.md:27` 仍为 MCP tool 56 active。
- Speaker 实测：`game_api.idl.yaml:55` 至 `:67` 存在 `ObjectiveType`，但 `codegen.md:26` 至 `:29` 仍写 MCP tool 56 active。
- 处置：D-H2 功能合同 CLOSED；API/DX 文档投影 PARTIAL，需要 `codegen.md` 计数更新，并在 api-registry 近旁或生成输出中暴露 `ObjectiveType` 链接/定义。

### ML-6 World tiers taxonomy

- `rev-dsv4-design-economy.md:40` 至 `rev-dsv4-design-economy.md:50`：DSV4 接受 3 primary tiers + Standard+/world.toml/Rhai modded 作为 MVP 简化。
- `rev-gpt-design-economy.md:53` 至 `rev-gpt-design-economy.md:69`：GPT 判 Medium GAP，认为 `Modded` 缺失导致产品/onboarding 语义不清。
- 处置：非 Blocker；补一行 `Modded` row 或“Modded 是 world.toml/Rhai override category”即可闭合。

### ML-4 host_path_find cache miss authority conflict

- `rev-dsv4-determinism-perf.md:168` 至 `rev-dsv4-determinism-perf.md:178`：DSV4 判 ML-4 CLOSED，`cache_miss_penalty = fixed 2000 fuel` 已写入 sandbox。
- `rev-gpt-determinism-perf.md:64` 至 `rev-gpt-determinism-perf.md:82`：GPT 判 PASS_WITH_CONFLICT，因 api-registry authoritative fuel table 缺 fixed 2000。
- Speaker 实测：`specs/core/04-wasm-sandbox.md:355` 有 2000 fuel；`specs/reference/api-registry.md:434` 至 `:442` 的 fuel table 未写 cache miss penalty。
- 处置：Medium authority drift；补 registry table 即可。

### ML-2 canonical-codec.md 引用文件缺失

- `rev-dsv4-determinism-perf.md:118` 至 `rev-dsv4-determinism-perf.md:150`：DSV4 判 GAP，`specs/reference/canonical-codec.md` 不存在。
- `rev-gpt-apidx.md:58` 至 `rev-gpt-apidx.md:65`：GPT API/DX 判 PASS，因为只验证了 inline semantics。
- Speaker 实测：`/data/swarm/docs/specs/reference/canonical-codec.md` 不存在。
- 处置：Medium；创建文件或移除外部引用并内联完整 canonical rules。

### ML-8 / ML-9 API/DX 机器可读合同

- `rev-dsv4-apidx.md:87` 至 `rev-dsv4-apidx.md:97`：ML-8 known incomplete；ML-9 prose closed，但缺 `schema_source` 字段。
- `rev-gpt-apidx.md:67` 至 `rev-gpt-apidx.md:91`：ML-8 FAIL，ML-9 FAIL/PARTIAL，因缺 machine-readable `alias_of` / `schema_source` 且 `swarm_auth_check` prose/table 不一致。
- 处置：Medium/High API-DX residual；若目标是 codegen 可执行合同，必须补机器字段。若只需人工说明，可降级为 Medium，但不能宣称完全 CLOSED。

## 已闭合项

| ID | 状态 | 支撑 reviewer |
|---|---|---|
| B1 scheduling chain delegation | CLOSED | DSV4 Architect、GPT Architect 均认可；link path hygiene 单独处理 |
| B3 WASM sandbox hardening | CLOSED | DSV4 Security、GPT Security 均认可 clone/pids.max/checklist/ABI failure semantics |
| B5 Auth/Deploy consistency | CLOSED_WITH_MINOR_HYGIENE | DSV4 Architect/Security、GPT Security 认可；GPT Architect 仅指出 stale section pointer |
| S-H2 refresh token grace hardening | CLOSED | DSV4 Security、GPT Security 均认可 FDB atomic grace/IP-UA/session family revoke |
| T-H1 seed lifecycle | CLOSED | Architect、Security、Determinism/Performance 两模型均认可 Arena commit-reveal + World seed-bump |
| E-H1 Allied Transfer intercept | CLOSED | DSV4 Architect、DSV4 Design/Economy、GPT Design/Economy、DSV4 Security 均认可 |
| D-H2 functional API | CLOSED_WITH_API_DX_RESIDUAL | Design/Economy 两模型认可；API/DX 要求补 registry/codegen 投影 |
| ML-1 256KB vs 1MB | CLOSED | DSV4 Determinism/Perf、GPT API/DX 均认可用途区分 |
| ML-3 ECS iteration CI | CLOSED | DSV4 Determinism/Perf、GPT Determinism/Perf 均认可 randomized entity iteration test |
| ML-4 fixed cache miss penalty | CLOSED_WITH_AUTHORITY_DRIFT | Sandbox 已闭合；api-registry 需同步 |
| ML-7 replay source privacy | CLOSED | Design/Economy 两模型均认可 default false + opt-in |
| ML-12 InsufficientResource cleanup | CLOSED for API/DX scope | DSV4 API/DX 确认 API docs clean；非 API doc residual 不在本轮主范围 |

## Medium/Low 处置

| ID | 问题 | 来源方向 | 处置 |
|---|---|---|---|
| M1 | `swarm_get_server_trust` auth tool 未注册到 Registry/IDL | Architect | Medium；补 `auth_api.idl.yaml` + registry |
| M2 | hard cap 1000 仍 benchmark-gated | Architect/Performance | Low/operational；保持标注，需 benchmark 后 production-ready |
| M3 | stale Auth section pointer “§3.4 Auth API 工具” | Architect/API-DX | Low；修正 intra-doc pointer |
| M4 | broken relative links | Architect | Medium；需用完整 `/data/swarm/docs` 路径重跑 link check，修真实锤坏链 |
| M5 | validation matrix 6 个非 canonical codes 未标 debug_detail | API/DX | Medium；标注或映射 canonical code |
| M6 | JSON-RPC error envelope IDL YAML 仍 `error.code string` | API/DX | Medium；同步为 numeric `-32000` + `data.rejection_reason` |
| M7 | `codegen.md` MCP tool count 仍 56 active | API/DX | High hygiene；改为 57 active 并纳入 CI drift check |
| M8 | `ObjectiveType` enum 未投影到 API Registry | API/DX | Medium；IDL 已有，registry/codegen 可见性需补 |
| M9 | `schema_source` / `alias_of` 只在 prose | API/DX | Medium/High；补机器可读字段或明确非 codegen contract |
| M10 | `canonical-codec.md` 缺失 | Determinism/API-DX | Medium；创建文件或移除引用 |
| M11 | `host_path_find` 2000 cache miss penalty 未进 registry fuel table | Determinism/Performance | Medium；同步 api-registry §4.4 |
| M12 | ML-6 缺 `Modded` tier 显式语义 | Design/Economy | Medium；补 row 或 normative sentence |
| M13 | Refresh token TTL 30d vs 7d | Security | Low/Info；统一 auth.md 与 api-registry |
| M14 | Arena CRL TTL 未进 api-registry | Security | Low/Info；补 5s cache TTL |
| M15 | TickTrace `wasmtime_version` vs `wasmtime_build_commit` 类型漂移 | Security | Low/Info；统一字段语义 |

## D-items（需用户裁决）

### D1: B4 worker queue deadline 语义

**问题**: 256 worker default + 500 active players 下，per-player 2500ms deadline 是否从 tick start 计时，还是从 worker 真正开始执行时计时？

**选项**:
- A. deadline 从 tick start 计时；queued player 若超时，本 tick 输出 0 command，记录 `TimeoutExceeded`。
- B. deadline 从 worker start 计时；同时必须降低 active_players 或提高 worker_pool_max，以保证 tick SLO 不被排队拖破。

**推荐**: A。它最小改动、保留 worker_pool_max=256，并让排队玩家也受同一 tick budget 约束。

### D2: S-H1 CSR 防护策略

**问题**: 是否接受 PoW-only CSR admission，还是补多维 admission control？

**选项**:
- A. 补 per-IP + global semaphore + bounded queue，PoW 作为第一层成本。
- B. 保留 PoW-only，但显式记录分布式 PoW 攻击风险接受、容量上限、监控指标与熔断策略。

**推荐**: A。PoW-only 对分布式来源不构成 admission control，且 R27 原要求即是多维防护。

### D3: ML-9 auth alias 是否必须 machine-readable

**问题**: Auth shortcut duplicate-prevention 目前 prose 已写，但 GPT API/DX 认为缺 `alias_of` / `schema_source` 无法被 codegen 可靠消费。

**选项**:
- A. 要求机器可读：给相关 registry/IDL rows 增加 `alias_of` / `schema_source` 字段。
- B. 接受 prose-only：codegen 不从该段自动生成 duplicate auth tools，人工维护。

**推荐**: A。该项本质是 API/DX/codegen 合同，应机器可读。

### D4: CX3 Rhai RuleMod ABI 的闭合标准

**问题**: DSV4 认为 single validation path + hooks/action buffer 已足够；GPT Architect 认为缺完整 hooks/helpers/capabilities/errors/version ABI。

**选项**:
- A. 将 CX3 闭合标准定义为“Rhai 不绕过 command validation”，当前基本闭合。
- B. 将 CX3 闭合标准定义为“可实现 RuleMod ABI”，需补完整 ABI section。

**推荐**: B。若要避免后续 mod 实现分叉，hooks/helpers/capabilities/errors/version 应形成单独合同。

## R29 入场条件

建议先修复以下 ultra-narrow 项，再开 R29 Closure Verification：

1. G1/G2/G3：CSR admission、CRL fallback 默认/枚举、`identity_fingerprint` schema。
2. G4：worker queue deadline 语义（D1 裁决后写入）。
3. G5：Dragonfly/NATS fan-out 并行或明确降级。
4. API/DX residual：`codegen.md` 57 active、ObjectiveType registry visibility、ML-8/ML-9 machine-readable status、D1 error envelope YAML。
5. Determinism residual：`canonical-codec.md` 文件、api-registry `host_path_find` cache miss penalty。
6. Hygiene：`swarm_get_server_trust` registry、stale links/pointers、ML-6 Modded tier sentence。

## 评审统计

- 总报告：10/10。
- Verdict 分布：0 CLOSED/APPROVE clean，4 CONDITIONAL_APPROVE/APPROVE_WITH_RESERVATIONS，6 PARTIALLY_CLOSED。
- 闭合强度：中等。核心架构与安全硬化大量收敛，但 API/DX 与身份/CSR 安全合同仍不宜冻结。
- 跨模型强一致 CLOSED：B3、B5、S-H2、T-H1、E-H1、ML-1、ML-3、ML-7。
- 跨模型强一致 GAP：S-H1、ML-10、ML-11、ML-5。
- 主要分歧项：B4 worker timeout（DSV4 critical vs GPT pass）、CX3 Rhai ABI（boundary vs implementable contract）、ML-6 tier taxonomy（implicit modded vs explicit row）、D-H2 enum visibility（IDL exists vs registry/codegen projection incomplete）。

## 最终裁决

**PARTIALLY_CLOSED**。

R28 证明 R27 的多数修复方向正确，但尚未达到“10/10 reviewer 均无实质 GAP”的 CLOSED 标准。下一轮应采用 ultra-narrow R29，仅验证：S-H1、ML-10、ML-11、B4 queue semantics、ML-5、API/DX projection、canonical-codec/host_path_find registry drift 与少量 hygiene 项。
