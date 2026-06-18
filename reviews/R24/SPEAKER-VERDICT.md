# Swarm 设计评审 R24 — Speaker Closure Verification 共识报告

## 裁决概要

- 本轮类型：Closure Verification（R5 pattern），不执行 Plan B 两级 CrossCheck；仅验证 R23 Blocker / D-items 是否已闭合。
- Reviewer 完成情况：14/14 份报告齐全，路径为 `/data/swarm/docs/reviews/R24/rev-*-*.md`。
- Phase 2 补漏情况：N/A。Closure Verification 模式不创建 CrossCheck 补充任务。
- 收敛评估：大部分 R23 项已闭合；但 B2 被 API/DX 与 Economy 两个方向、GPT 与 DeepSeek 两类模型共同指出仍存在事实源/参数一致性 GAP，其中 GPT Economy 判定为 Critical。另有 GPT Determinism 指出 B3 特殊攻击同 tick 优先级合同冲突。
- Freeze 状态：未冻结。需至少闭合 B2 后再进入下一轮 Closure Verification；建议同时处理 B3 优先级冲突。

## 总体 Verdict

REQUEST_MAJOR_CHANGES

理由：R23 B2 未闭合，且属于跨方向（API/DX + Economy）与跨模型（GPT-5.5 + DeepSeek V4 Pro）确认的单事实源/参数一致性缺陷。该问题会让实现者、SDK/codegen、经济实现读取到不同事实，不能作为可冻结合同。

## 逐项 Closure 状态

| R23 项 | R24 Speaker 状态 | 交叉验证证据 | 说明 |
|---|---:|---|---|
| B1: World 经济启动 | CLOSED | rev-gpt-architect、rev-dsv4-architect、rev-gpt-designer、rev-dsv4-designer、rev-gpt-economy、rev-dsv4-economy | starting_resources、free_upkeep、growth path、repair cap / distance decay 在 Resource Ledger、Balance Sheet、API Registry 中均有落点。 |
| B2: API 单事实源 / 参数一致性 | GAP | rev-gpt-apidx=GAP、rev-gpt-economy=GAP Critical、rev-dsv4-economy=GAP；rev-dsv4-apidx=闭合但未覆盖计数/经济残留 | API 计数、Registry 派生表、经济参数仍存在多处冲突。此项未闭合。 |
| B3: 确定性合同 | GAP | 多数评审判 CLOSED；rev-gpt-determinism 指出特殊攻击/Disrupt 同 tick 优先级冲突 | 核心确定性合同、SIMD、D5/A 已大体闭合，但 `02-command-validation.md` 与 `06-phase2b-system-manifest.md` 的特殊攻击优先级不一致，需要统一权威顺序。 |
| B4: 容量证明 | CLOSED | rev-gpt-architect、rev-dsv4-architect、rev-gpt-performance、rev-dsv4-performance、rev-gpt-security、rev-dsv4-security、rev-gpt-determinism、rev-dsv4-determinism | 9 项 benchmark gate、tick pipeline budget、500/1000 active player 推导、room partition、fair-share admission 均有明确证据。 |
| D1/A: starting_resources + free_upkeep | CLOSED | rev-gpt-designer、rev-dsv4-designer、rev-gpt-economy、rev-dsv4-economy、architect 双模型 | `{Energy: 5000, Minerals: 2000}`、1 controller、3 drones、2000 ticks、一次性身份约束均被验证。 |
| D2/B: 三层 drone cap + debug_detail | CLOSED | rev-gpt-apidx、rev-dsv4-apidx、rev-gpt-performance、rev-dsv4-performance | per-player 50、per-room 500、global 10,000；`RoomDroneCapReached` 和 `debug_detail` 机制已记录。 |
| D3/A: Disrupt body part match | CLOSED | rev-gpt-designer、rev-dsv4-designer、rev-dsv4-determinism | validation 与 application/manifest 层均有 body part match 证据。注意：这不消除 B3 的同 tick 优先级冲突。 |
| D4/A: Controller repair cap/distance decay | CLOSED | designer 双模型、economy 双模型 | `repair_cap=3500bp`、`distance_decay_bp=500bp/tile`，Balance Sheet 与 Registry 同步。 |
| D5/A/B: replay-critical subset + async object-store | CLOSED | rev-gpt-security、rev-dsv4-security、rev-gpt-determinism、rev-dsv4-determinism、architect 双模型 | FDB replay-critical 原子字段、debug/rich async blob、失败语义、orphan cleanup 均已定义。 |
| D6/B: room-partition / benchmark gate | CLOSED | performance 双模型、security 双模型、architect 双模型 | FDB room partition、2PC、事务大小、benchmark gate 与失败语义均已定义。 |

## 共识 Blocker（跨方向 + 跨模型同意）

### B2-GAP: API/经济单事实源仍有可见漂移

**方向 × 模型矩阵**:
- API/DX × GPT-5.5：GAP
- Economy × GPT-5.5：GAP Critical
- Economy × DeepSeek V4 Pro：GAP
- API/DX × DeepSeek V4 Pro：CLOSED，但其证据侧重权威声明/codegen gate，未覆盖 GPT/API 与 Economy 指出的残留计数和经济派生表冲突

**问题**:
- `api-registry.md`、`codegen.md`、`mcp-tools.md`、`design/interface.md` 中仍存在 API 数量不一致：54/56 game tools、19/21 CommandAction、47/79 RejectionReason 等冲突。
- `api-registry.md` §5.7 仍使用 storage tax 旧绝对阈值 10,000 / 100,000 / 1,000,000，而 Resource Ledger 与 `api-registry.md` §10.2 使用容量百分比 tier 30% / 60% / 85% / 100%。
- `design/gameplay.md` 仍保留旧 empire-upkeep 示例与 transfer delay 数字；与 Resource Ledger / Balance Sheet 的权威公式和 `global_transfer_delay=100 tick` 不一致。
- `08-resource-ledger.md` §6 对 Recycle 公式引用小节错位，削弱可追踪性。

**修正要求**:
1. 以 YAML IDL / `api-registry.md` 权威表为准，统一所有派生文档中的工具数、CommandAction 数、RejectionReason 数；移除或改写手写计数，避免再次漂移。
2. 修正 `api-registry.md` §5.7 的 storage tax 旧绝对阈值，改为百分比 tier 或直接引用 §10.2 / Resource Ledger。
3. 修正 `design/gameplay.md` 的旧 empire-upkeep 示例和 transfer delay 数值；若 gameplay 只是设计说明，应引用 Resource Ledger / Balance Sheet，而非重复硬编码参数。
4. 修正 `08-resource-ledger.md` §6 Recycle 公式引用。
5. 运行或定义可执行的 drift check：IDL → registry/codegen 输出与所有引用文档不得保留手写冲突事实。

## 确定性补充 GAP

### B3-GAP: 特殊攻击同 tick 优先级合同冲突

**来源**：rev-gpt-determinism

**分歧状态**：非跨模型共识，但证据具体，且影响 replay/跨实现一致性，因此 Speaker 将其记录为需闭合 GAP，而非忽略。

**问题**:
- `02-command-validation.md` §3.16 声明同 tick 多命中优先级为 `Disrupt → Fortify → Debilitate → Hack → Drain/Leech → Overload → Fabricate`。
- `06-phase2b-system-manifest.md` §S14 reducer resolve 声明优先级链为 `Hack > Drain > Overload > Debilitate > Disrupt > Fortify`。
- `06-phase2b-system-manifest.md` 又自称 tick 系统执行顺序唯一权威，因此该冲突会使不同实现者按不同顺序 resolve 特殊攻击，造成状态推进和 replay 分叉风险。

**修正要求**:
1. 选择唯一权威优先级顺序。
2. 在另一个文档中删除重复顺序或改为引用权威文档。
3. 将该顺序纳入 determinism/replay 测试样例，覆盖同 tick 多特殊攻击命中。

## CrossCheck 补漏发现（基于 Phase 2）

无补漏发现。R24 是 Closure Verification，全量编号项验证模式，不执行 Phase 2 CrossCheck。

## 方向专属 High 优先级

### X-H1: API 数量与派生文档 drift

**来源**：rev-gpt-apidx

**状态**：归入 B2-GAP。

**证据摘要**：Registry §3 / changelog、`codegen.md`、`mcp-tools.md`、`design/interface.md` 对 game tools、CommandAction、RejectionReason 数量仍有冲突。

### E-H1: 经济参数跨文档冲突

**来源**：rev-gpt-economy、rev-dsv4-economy

**状态**：归入 B2-GAP。

**证据摘要**：旧 upkeep 示例、transfer delay、storage tax thresholds、Recycle 引用仍未完全收敛。

### T-H1: 特殊攻击优先级冲突

**来源**：rev-gpt-determinism

**状态**：记录为 B3-GAP。

**证据摘要**：`02-command-validation.md` 与 `06-phase2b-system-manifest.md` 对同 tick 多特殊攻击优先级给出不同顺序。

## Medium/Low 处置

| ID | 问题 | 来源方向 | 处置 |
|---|---|---|---|
| M1 | `08-resource-ledger.md` §6 Recycle 公式引用错位 | Economy GPT | Low，但作为 B2 修正包一并处理。 |
| M2 | `api-registry.md` §5.7 generated summary 未再生成 | Economy DeepSeek | Medium；若确认为生成产物，应通过 codegen 修复而非手改后遗忘。 |
| M3 | SIMD opt-in deterministic subset 仍需跨架构 CI 证明 | Security/Performance/Determinism 多方 | Implementation-phase guard；当前 CV 判 CLOSED，不列为 blocker。 |

## D-items（需用户裁决）

本轮 Closure Verification 未发现新的必须用户二选一裁决项。现有 D1–D6 的裁决状态如下：

### D1/A: World 启动资源与免维护

**状态**：CLOSED

**证据**：Resource Ledger、Balance Sheet、API Registry 均记录 starting_resources 与 free_upkeep 参数。

### D2/B: 三层 drone cap + debug_detail

**状态**：CLOSED

**证据**：API/DX 双模型与 Performance 双模型确认 per-player/per-room/global 三层 cap 与 `RoomDroneCapReached` / `debug_detail` 设计。

### D3/A: Disrupt body part match

**状态**：CLOSED

**证据**：Designer 双模型与 Determinism DeepSeek 确认 validation/application 两层 body part match。

### D4/A: Controller repair cap/distance decay

**状态**：CLOSED

**证据**：Designer/Economy 双方向确认 `repair_cap=3500bp`、`distance_decay_bp=500bp/tile`。

### D5/A/B: Replay-critical 与 object-store async

**状态**：CLOSED

**证据**：Security/Determinism 双方向确认 FDB 原子提交与 async blob 失败语义。

### D6/B: Room partition / benchmark gate

**状态**：CLOSED

**证据**：Performance/Security/Architect 多方向确认 room partition、2PC、9 项 benchmark gate。

## 文档维护项

1. 补齐或恢复 R23 verdict 可追溯路径：本次 Speaker 尝试读取 `/data/swarm/docs/reviews/R23/SPEAKER-VERDICT.md` 与 `/data/swarm/docs/reviews/R23/`，当前路径不可见；R24 仍可基于任务正文和 14 份 reviewer 报告完成裁决，但建议维护 reviews index，避免历史裁决文件不可追溯。
2. 更新 R24 reviews index（如存在 `docs/reviews/README.md`）：记录本轮 REQUEST_MAJOR_CHANGES 与主要 GAP。
3. B2 修复后建议运行一次窄范围 R25 Closure Verification：API/DX + Economy + Determinism 至少复核 B2/B3；若坚持 14/14 规则，则完整 R25 CV。

## 评审统计

| Direction | GPT-5.5 verdict | DeepSeek V4 Pro verdict | Speaker 采信摘要 |
|---|---|---|---|
| Architect | APPROVE | APPROVE | B1/B3/B4 大体闭合证据充分。 |
| Security | APPROVE | APPROVE | B3 SIMD/D5 与 B4 容量安全边界闭合。 |
| Designer | APPROVE | APPROVE | B1 与 D3 闭合。 |
| Performance | APPROVE | APPROVE | B3 SIMD 与 B4 容量/room partition/drone cap 闭合。 |
| Economy | REQUEST_MAJOR_CHANGES | CONDITIONAL_APPROVE | B1 闭合；B2 未闭合。GPT 认为 Critical，DeepSeek 认为 non-blocking，但均确认 GAP。 |
| API/DX | CONDITIONAL_APPROVE | APPROVE | D2/B 闭合；B2 权威声明存在，但 GPT 指出计数/派生文档 drift。 |
| Determinism | CONDITIONAL_APPROVE | APPROVE | B4 闭合；B3 多数子项闭合，但 GPT 指出特殊攻击优先级冲突。 |

### 共识强度评估

- Strong CLOSED：B1、B4、D1、D2、D3、D4、D5、D6。
- Strong GAP：B2。至少 3 份报告直接确认 GAP，覆盖 API/DX 与 Economy 两方向；其中 1 份为 REQUEST_MAJOR_CHANGES。
- Weak/Isolated GAP but actionable：B3 特殊攻击优先级冲突。虽然只有 GPT Determinism 明确提出，但证据具体、影响确定性合同，需在下一轮前处理。

## R25 入场条件

1. B2-GAP 全部修复，并提供 drift check 或明确引用策略证明。
2. B3-GAP 特殊攻击优先级统一，并同步 validation / manifest 文档。
3. 重新运行 Closure Verification；若目标是正式 Freeze，必须继续保持 14/14 reviewer 完整性。
