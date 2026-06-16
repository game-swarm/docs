# Swarm 设计评审 — Speaker 共识报告

> Round: R6 clean-slate design review  
> Speaker: rev-speaker  
> 输入完整性: 9/9 评审官已纳入。4 份报告存在于 `/data/swarm/docs/reviews/R6/` 或工作区；5 份来自 Kanban 父任务 handoff / comment，其中 `rev-dsv4-designer` 虽无落盘文件但有结构化 review-required handoff。

## 裁决概要

R6 是一次 clean-slate 全量设计评审，不依赖 R5 历史闭合结论。9 名评审官总体高度认可当前设计的核心方向：WASM-only gameplay、MCP 作为管理/观察界面而非 gameplay executor、Source Gate、统一可见性函数、确定性 tick pipeline、Rhai 规则模组信任链、Arena/World/PvE 分层等均被多名评审官列为亮点。

但本轮没有达到 Freeze。原因不是总体架构方向错误，而是仍存在若干会阻塞实现或破坏平衡/安全边界的合同缺口：

- `design/gameplay.md` 源文件含真实 `[OUTPUT TRUNCATED ...]` 占位符，导致 Vanilla Ruleset 的 body part / Leech / Fabricate 关键定义物理缺失。
- Phase 2b ECS 主链、特殊攻击优先级、Spawn 资源扣除等核心 tick 语义仍有跨文档/跨阶段不一致。
- Fabricate、Drain、Hack、Overload 等特殊攻击在 gameplay balance 与 visibility/security 上有多方交叉风险。
- Tier 2/3、dynamic IDL/SDK、Rhai custom handler、sandbox worker model 等扩展能力的 entry gate 仍需收紧，避免污染 Tier 1 MVP。

Freeze 状态: **NOT FROZEN**。Tier 1 MVP 方向可保留，但进入实现前必须先修正文档级 Blocker。

## 总体 Verdict

**REQUEST_MAJOR_CHANGES**

判定理由：9 名评审中 8 名给出 `CONDITIONAL_APPROVE`，1 名（rev-claude-designer）给出 `REQUEST_MAJOR_CHANGES`。若只看投票，可接近 conditional approve；但 Speaker 按“跨方向 + 跨模型 + 可实现性”聚合后，发现至少 4 个问题被多个方向/模型共同触及，且其中 `design/gameplay.md:624` 的源文件截断是客观存在的实现阻断。因此本轮 Verdict 升级为 `REQUEST_MAJOR_CHANGES`，要求修正文档后再进入下一轮评审或实施。

## 共识 Blocker (跨方向 + 跨模型同意)

### B1: Vanilla Ruleset 关键定义物理缺失，Fabricate/Leech/Body Part 合同不完整

**方向 × 模型矩阵**:
- Designer / Claude: Critical G1，指出 `design/gameplay.md:624` 含 `[OUTPUT TRUNCATED]` 字面量，丢失 body part 与 Leech/Fabricate 规则。
- Designer / GPT: High G1，指出 Overload reference 与 gameplay/security 冲突；同时要求特殊攻击 reference 对齐。
- Designer / DeepSeek: High/Medium-High，指出经济闭环模型、Energy-Fuel 等价合同、Fabricate swing 风险。
- Security / DeepSeek: High H2，指出 Leech/Fabricate 缺 command validation specs。
- Architect / GPT: High A2，指出 dynamic CommandAction/IDL/SDK 抽象过强，Tier 1 不应依赖动态 action 体系。

**问题**:
`design/gameplay.md:624` 经本轮实际验证，确实包含 `... [OUTPUT TRUNCATED - 1675 chars omitted out of 51675 total] ...` 字面量。这不是展示层截断，而是源文件内容损坏。该位置处于特殊攻击表格与 `[[body_part_types]]` 默认规则之间，导致 Vanilla Ruleset 最基础的实现常量和特殊攻击合同无法作为实现依据。

同时，Fabricate 的 `structure_type`、成本、RCL、max_per_room、target 类型、领土归属、反制窗口未闭合；Leech/Fabricate 也被多名评审指出缺少 validation/spec/reference 对齐。

**修正要求**:
1. 从 git 历史或可信来源恢复 `design/gameplay.md` 截断段，补齐 Leech/Fabricate 表格和全部核心 body part 默认定义。
2. 为 Fabricate 写明最小合同：允许的 target kind、structure_type 白名单、额外结构成本、RCL/max_per_room 校验、放置领土约束、是否占 main action、反制窗口。
3. 将 Leech/Fabricate 加入 command validation / API IDL / reference 的同一真相链，避免 gameplay 表格与 reference 分叉。
4. 增加文档 CI guard：禁止 `OUTPUT TRUNCATED`、`chars omitted` 等工具截断标记进入 docs。

### B2: Phase 2b / tick 执行语义尚未冻结，影响确定性实现

**方向 × 模型矩阵**:
- Architect / Claude: High A1，指出 Phase 2b ECS chain 在 design/engine、specs/01、specs/02、specs/07 中出现多个版本。
- Architect / DeepSeek: High D1，指出 Phase 2b chain 缺 `spawning_grace` + `status_advance`。
- Architect / GPT: Strength 认可三段 tick，但 High/Medium 要求 Tier/transaction boundary 更明确。
- Designer / Claude: Strength S3 依赖 `death_mark → spawn → spawning_grace → combat → status_advance`；若主链不一致则该设计亮点不可实现。

**问题**:
核心执行链在多个文档里不一致，尤其是 regeneration/decay 与 combat 的先后关系、`spawning_grace`、`status_advance` 是否在主链中。特殊攻击 §3.16 优先级与 §3.1 inline command loop 的关系也未定义。Spawn 的 body_cost 是 Phase 2a 立即扣除还是 Phase 2b 创建时扣除，同样影响同 tick 双花与 rollback 语义。

**修正要求**:
1. 选定一个权威 Phase 2b chain，并同步 `design/engine.md`、`specs/core/01`、`specs/core/02`、`specs/core/07` 示例。
2. 明确 regeneration/decay 与 combat 的先后关系，避免同 tick 资源/伤害结算出现实现分叉。
3. 明确特殊攻击优先级是覆盖全局 command loop，还是仅为单 effect set 内部顺序。
4. 明确 Spawn body_cost 扣除时点和 Phase 2b 创建失败退款路径。

### B3: 可见性 / oracle 防线仍有跨接口缺口

**方向 × 模型矩阵**:
- Security / GPT: High，MCP `player_view=full` 与 fog-of-war / WASM snapshot 形成可见性 oracle。
- Security / Claude: High H2，`omitted_count` 精确暴露被截断实体数；Medium M1/M2/M3/M5 涉及 rejection/dry-run/explain oracle。
- Designer / GPT: High G1，Overload reference 暴露 fuel 下限、无 range 限制，形成 fuel oracle / harassment。
- Architect / Claude/GPT: Medium，snapshot truncation、Overload visibility 派生函数、Tier 1 truncation contract 不完整。

**问题**:
设计已确立 `is_visible_to` 统一函数和 visibility-first 原则，但若 MCP full view、dry_run/simulate、explain_last_tick、omitted_count、Overload rejection reason 等接口不统一脱敏，AI/玩家仍可通过管理/调试/反馈接口间接绕过 fog-of-war。

**修正要求**:
1. 明确 competitive world 中 MCP read/query 不得超过 WASM snapshot 的可见范围；`player_view=full` 仅限 human/spectator 或 non-competitive 配置。
2. 将 `omitted_count` / `total_visible_count` 改为分桶或 unknown，不提供精确数量 oracle。
3. dry_run / simulate / explain_last_tick 必须复用 player-facing redaction policy。
4. Overload/Hack/Drain 等特殊攻击 rejection reason 必须遵循 `NotVisibleOrNotFound` / `NotEligible` 等等价返回策略。

### B4: Tier 1 MVP 与 Tier 2/3 / dynamic extensibility entry gate 混杂

**方向 × 模型矩阵**:
- Architect / GPT: High A1/A2/A3，要求 Tier 1 只保留固定 Core IDL、内置 action、内置 handler；dynamic SDK/Rhai handler 进入 Tier 2+ gate。
- Architect / Claude: High A2，Tier 3 LWW + FDB versionstamp 与 Determinism Contract 冲突。
- Architect / DeepSeek: 多项 consistency/algorithmic risks，核心为 Phase 2b 和扩展路线边界。
- Security / GPT/Claude: sandbox、CVE-SLA、Gateway transport、Rhai action boundary 都要求实施前明确安全边界。

**问题**:
文档同时声明 Tier 1 可实施、Tier 2/3 future specs 需冻结、dynamic CommandAction/SDK、Rhai custom handler、Tier 3 cross-shard conflict 等高级能力。这些能力方向可取，但若不明确 feature gate，会让 MVP 实现被未来扩展污染，或让实现者误以为必须先冻结分片/动态语言平台才能编码。

**修正要求**:
1. 建立 Tier entry gate 矩阵：Tier 1 必须冻结哪些合同，Tier 2/3 仅在对应能力启用前冻结。
2. Tier 1 固定 Core IDL + 内置 action/handler；dynamic CommandAction、world-specific SDK、Rhai custom handler 标为 Tier 2+ 或 future-disabled。
3. Tier 3 放弃物理 versionstamp 作为确定性 tie-breaker，改用逻辑时钟，或明确跨分片不保证 tick-by-tick replay determinism。
4. 将 rollback/admin、sandbox worker pool、Wasmtime upgrade runbook 等运维能力标明是否 MVP 范围。

## 方向专属 High 优先级

### A-H1: Architect — ECS 主链与 Tier 边界需先冻结

Architect 组三名评审都认为总体架构方向可实施，但主链排序、Tier gate、dynamic extensibility 和 Tier 3 determinism 是进入实现前必须收紧的合同。该方向没有要求推翻架构，而是要求防止“future architecture blocks MVP”。

### S-H1: Security — Transport / Identity / Sandbox / Visibility 的边界语义需统一

Security 组三名评审均为 `CONDITIONAL_APPROVE`，说明安全骨架可接受；但 Gateway transport 鉴权、JWT/证书有效期、sandbox syscall/namespace、visibility oracle、dry-run/simulate redaction 等若不统一，会直接变成实现漏洞。

### D-H1: Designer — 特殊攻击经济和平衡存在实现前阻断

Designer 组分歧最大：GPT 与 DeepSeek 为 `CONDITIONAL_APPROVE`，Claude 为 `REQUEST_MAJOR_CHANGES`。Speaker 采纳 Claude 的升级理由，因为源文件截断可客观验证，Fabricate/Drain/Hack 等机制也被其他评审以不同角度触及。Designer 方向要求在进入实现前补齐 Vanilla Ruleset 与特殊攻击平衡合同。

## Medium/Low 处置

| ID | 问题 | 负责 Phase | 处置 |
|---|---|---|---|
| M1 | Wasmtime/CVE 升级 runbook 与重编译预算 | Phase 1 ops design | 扩展 CVE-SLA，列依赖范围与批量重编译/只读模式 |
| M2 | Gateway DNS rebinding / reverse proxy 拓扑表述不清 | Phase 1 gateway | 明确 localhost/unix socket behind reverse proxy 模式 |
| M3 | Replay share metadata / social graph | MVP+ gameplay/community | 非阻塞，进入 community backlog |
| M4 | MCP resource manifest / AI 教程资源目录 | Phase 1 onboarding | 补 canonical URI、schema、SDK/example artifact 合同 |
| M5 | Long-term identity layer / 成就 / curator reputation | MVP+ design | 非阻塞，作为长期留存设计补强 |
| M6 | Tutorial recycle 100% 与 lifespan refund 公式冲突 | Phase 1 gameplay | 明确 Tutorial 特例优先级或禁 spawn-recycle 套利 |
| M7 | Vanilla tier 特殊攻击一次性解锁断崖 | Balancing pass | 建议渐进解锁，但不阻塞 Tier 1 engine 实现 |
| M8 | Rhai `damage_entity` 目标范围与抗性路径 | Phase 1 world rules | 明确 entity type、resistance、grace/fortify、TickTrace |
| M9 | Admin rollback lifecycle | Phase 1+ ops | 若不做 MVP，Gateway topic 标 future-disabled |
| M10 | GETTING-STARTED command schema drift | Docs polish | 对齐 canonical schema 或标明 SDK wrapper |

## 文档维护项

1. 创建/更新 `/data/swarm/docs/reviews/R6/` 索引，并将分散 artifact 归档到 R6 目录；当前已有 4 份文件，另有部分只存在工作区或 Kanban handoff。
2. 将 `/data/swarm/docs/review-rev-claude-security-R6.md` 移入 `/data/swarm/docs/reviews/R6/rev-claude-security.md` 或在索引中链接，避免游离文件。
3. 为 `rev-dsv4-designer` 从 Kanban comment 生成正式 `/data/swarm/docs/reviews/R6/rev-dsv4-designer.md`，否则后续纯文件审计会误判缺席。
4. 将 gpt-architect 工作区 artifact 复制/归档到 `/data/swarm/docs/reviews/R6/rev-gpt-architect.md`。
5. 补充文档 CI/sanity checks：禁止 `[OUTPUT TRUNCATED`、检查 9/9 review artifacts、检查 required review path。

## 评审统计

### 3×3 Verdict 矩阵

| Direction | Claude Opus 4.7 | GPT-5.5 | DeepSeek V4 Pro |
|---|---|---|---|
| Architect | CONDITIONAL_APPROVE | CONDITIONAL_APPROVE | CONDITIONAL_APPROVE |
| Security | CONDITIONAL_APPROVE | CONDITIONAL_APPROVE | CONDITIONAL_APPROVE |
| Designer | REQUEST_MAJOR_CHANGES | CONDITIONAL_APPROVE | CONDITIONAL_APPROVE |

### Severity 摘要

| Reviewer | Critical | High | Medium | Low/Info | 来源 |
|---|---:|---:|---:|---:|---|
| rev-claude-architect | 0 | 3 | 5 | 5+missing | `/data/swarm/docs/reviews/R6/rev-claude-architect.md` |
| rev-gpt-architect | 0 | 3 | 3 | 1+missing | workspace artifact |
| rev-dsv4-architect | 0 | 1 | 3 | 2 | parent handoff |
| rev-claude-security | 0 | 2 | 5 | 6 | `/data/swarm/docs/review-rev-claude-security-R6.md` |
| rev-gpt-security | 0 | 3 | 3 | 1 | `/data/swarm/docs/reviews/R6/rev-gpt-security.md` |
| rev-dsv4-security | 1 | 3 | 5 | 4 | parent handoff |
| rev-claude-designer | 3 | 5 | 7 | 8+missing | `/data/swarm/docs/reviews/R6/rev-claude-designer.md` |
| rev-gpt-designer | 0 | 1 | 3 | 1+missing | `/data/swarm/docs/reviews/R6/rev-gpt-designer.md` |
| rev-dsv4-designer | 0 | 1 | 4+ | 3 | Kanban comment |

### 共识强度评估

- **强共识**: 核心方向正确，MCP 非 gameplay、WASM-only、统一 visibility、Source Gate、determinism、World/Arena/PvE 分层均应保留。
- **强阻塞**: Vanilla Ruleset 源文件截断 + 特殊攻击合同缺失，已达到客观实现阻断。
- **中强阻塞**: Phase 2b 主链、Spawn 扣费、特殊攻击优先级属于实现者必需的确定性语义，不应拖到代码阶段自行解释。
- **中强安全风险**: visibility oracle 问题跨 MCP / snapshot / dry-run / explain / special attacks，必须在文档层统一 redaction invariant。
- **需用户裁决**: Tier 3 是否坚持 tick-by-tick replay determinism；若坚持，必须放弃 physical versionstamp tie-breaker；若不坚持，需要明确 Tier 3 的 replay 降级语义。

## 下一轮入场条件

R7 或实现前复审应至少满足：

1. `design/gameplay.md` 截断段恢复，且 grep 不再命中 `OUTPUT TRUNCATED`。
2. Fabricate/Leech/body parts 在 design、validation、IDL/reference 中一致。
3. Phase 2b 主链、special attack priority、Spawn 扣费时点跨文档一致。
4. MCP/visibility/dry-run/explain/omitted_count 统一脱敏策略。
5. Tier entry gate 明确，Tier 1 MVP 不依赖动态 SDK/Rhai handler/Tier 3 分片合同。

满足以上后，预期 Verdict 可回落到 `CONDITIONAL_APPROVE` 或 `APPROVE_WITH_RESERVATIONS`；若 Fabricate/Drain/Hack 平衡也同步闭合，可重新考虑 Freeze。
