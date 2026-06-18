# Swarm 设计评审 R25 — Speaker 共识报告

## 裁决概要
- 本轮类型：Closure Verification，仅验证 R24 残留 B2/B3 是否闭合，不引入开放式新议题。
- Phase 1 完成情况：14/14 reviewers 已完成，报告路径为 `/data/swarm/docs/reviews/R25/rev-*-*.md`。
- Phase 2 补漏情况：本轮为 Closure Verification 回退模式，不使用 Plan B CrossCheck/Phase 2；无补漏任务。
- 收敛评估：B3 在可读权威文档中实质闭合；B2 在 Recycle 与 upkeep 残留上仍有跨方向、跨模型可验证 GAP。
- Freeze 状态：不得 Freeze。R25 未达到 B2/B3 双闭合条件。

## 总体 Verdict

REQUEST_MAJOR_CHANGES

理由：B3 可判 CLOSED，但 B2 仍存在 Blocking GAP。B2 的残留不是单个 reviewer 的读取范围问题，而是在 `design/gameplay.md`、`specs/core/02-command-validation.md`、`specs/reference/commands.md` 中仍能直接读到与 Resource Ledger / API Registry 权威公式冲突的旧语义。Closure Verification 的通过条件是 B2 与 B3 均 CLOSED；当前不满足。

## 共识 Blocker (跨方向 + 跨模型同意)

### B2: API/经济单事实源仍未完全闭合

**方向 × 模型矩阵**:
- GPT-5.5: Architect / Security / API-DX / Economy / Designer / Determinism 均判 B2=GAP；Performance 的 B2=GAP 主要来自读取范围过窄，低权重记录。
- DeepSeek V4 Pro: Architect / Security / API-DX / Economy / Designer / Determinism / Performance 均判 B2=CLOSED。
- Speaker 证据裁定：采纳 GPT 系列指出的可验证残留；DeepSeek 系列多聚焦权威公式已存在，但漏检派生/正文旧语义仍并存。

**问题**:
1. `specs/core/02-command-validation.md:288` 的 Recycle 主命令段仍写明“返还 50% 身体部件成本作为能量给 spawn”，而同文件 `specs/core/02-command-validation.md:483` 起的 §3.18 定义 lifespan-proportional 10%–50% 公式。两套规则同文件并存，且 §3.9 未明确委托 §3.18。
2. `specs/core/02-command-validation.md:708` 起的旧 CommandAction 变体仍写“标准退还 | body part spawn 总成本的 50%”与 Tutorial 100% 退还，未引用 lifespan 公式。
3. `specs/reference/commands.md:114` 起仍在 API/DX 展示文档中写 Recycle “退还 50% body part 资源 / body_cost(body) × 0.5”，与 `specs/reference/api-registry.md:738`、`specs/reference/api-registry.md:752` 的 canonical formula 冲突。
4. `design/gameplay.md:106`、`design/gameplay.md:108`、`design/gameplay.md:410` 附近仍以固定 50% 描述 Recycle；这与 `design/economy-balance-sheet.md:151` 起的 Resource Ledger 单一权威声明不一致。
5. `design/gameplay.md:1998` 起的“帝国维护费示例效果”仍保留 40/275/2100/3150 per tick 与“待 B6 闭合时产出”等旧说明；与 `design/economy-balance-sheet.md:20` 起的 Standard 55/375/3000/15000 per tick 派生验证表不一致，也削弱 upkeep 单事实源闭合。

**修正要求**:
- 将所有 Recycle 用户可见描述和命令参考改为引用唯一公式：`refund_rate_bp = max(1000, remaining_lifespan * 5000 / total_lifespan)`，clamp [10%, 50%]，`refund_amount = refund_rate_bp * body_cost / 10000`；如果 Tutorial 仍有 100% 例外，必须标为 world-mode override，并说明优先级与权威位置。
- 改写 `02-command-validation.md` §3.9 与 §10.3：不得重复固定 50%，只保留校验项与指向 §3.18 / Resource Ledger / API Registry 的引用。
- 改写 `specs/reference/commands.md` Recycle 展示：不得写 `body_cost × 0.5`，改为 lifespan-proportional，并链接 API Registry canonical formula。
- 改写 `design/gameplay.md` Drone 身体规划与经济分类账中的固定 50% 表述；必要时写“最高 50%，随剩余 lifespan 递减至 10%”。
- 改写或删除 `design/gameplay.md` “帝国维护费示例效果”中的旧 40/275/2100/3150 数值与“待 B6 闭合”说明；若保留示例，必须明确从 Resource Ledger 当前 Standard/Vanilla 参数派生，并与 Economy Balance Sheet 同步。

## CrossCheck 补漏发现（基于 Phase 2）

无补漏发现。本轮为 Closure Verification，不执行 CrossCheck/Phase 2。

## B2/B3 闭合裁定

### B2: GAP

**共识强度**: High。虽然模型投票呈 7 APPROVE vs 7 REJECT，但实质证据支持 GAP：至少 5 个方向的 GPT reviewer 独立指出 Recycle 固定 50% 残留；Economy 方向额外指出 gameplay upkeep 旧示例残留。Speaker 复核确认这些文本当前仍存在。

**实质已闭合部分**:
- Storage tax 已从旧绝对 10K 阈值迁移为 percentage-based tiers，`design/gameplay.md:340` 起与 `api-registry.md:738` 起均指向 30%/60%/85%/100% capacity 模型。
- API Registry 已有 Economy Operations 与 Canonical Formulas，`RecycleRefund`、`StorageTax`、`UpkeepDeduction` 的权威公式框架已经建立。
- Economy Balance Sheet 已声明 Resource Ledger 为所有收支计算单一权威源。

**未闭合部分**:
- Recycle 仍有固定 50% 旧语义残留，且残留分布于核心命令规范、参考命令文档和设计文档。
- Gameplay upkeep 的旧示例数值与当前 Economy Balance Sheet 派生表冲突，且包含“待 B6 闭合”过期说明。

### B3: CLOSED

**共识强度**: High。Architect / Security / Determinism / API-DX 的多数报告均确认 B3 已闭合；Speaker 复核权威文件后确认。

**闭合证据**:
- `specs/core/02-command-validation.md` §3.16 明确声明特殊攻击优先级以 `06-phase2b-system-manifest.md` §S14 为唯一权威，并要求不得从该文档复制/粘贴优先级链。
- `specs/core/06-phase2b-system-manifest.md:181` 起的 S14 `special_attack_reducer` 明确唯一权威链：Hack > Drain > Overload > Debilitate > Disrupt > Fortify。
- `specs/core/06-phase2b-system-manifest.md:216` 起的 Special Attack Unique Writer Contract 定义 status component、PendingIntents、special attack damage 的唯一 writer，支撑 B3 的执行层闭合。

**对少数 GAP 判定的处置**:
- `rev-gpt-designer` 与 `rev-gpt-performance` 的 B3=GAP 主要基于允许读取文件中没有 S14 证据，而非发现权威文件中存在冲突表。Speaker 直接复核权威文件后，将其记录为读取范围导致的低权重不确定性，不升级为 B3 blocker。

## 方向专属 High 优先级

### A-H1: `02-command-validation.md` Recycle 同文件双语义
架构风险：§3.9 固定 50% 与 §3.18 lifespan formula 并存，读者或实现者可选择不同规则，导致实现分叉。

### S-H1: Recycle 经济套利约束未在主命令段闭合
安全/经济风险：lifespan 末期回收应降至 10%，但主命令段仍写固定 50%，削弱 aging → death → 资源损失约束。

### D-H1: Gameplay 层固定 50% 与旧 upkeep 示例残留
设计风险：玩家-facing 设计文档仍传达旧经济直觉，误导 body planning 与 empire upkeep 预期。

### P-H1: 读取范围不足的 Performance 判定不可作为实质证据
流程风险：`rev-gpt-performance` 仅读 README 后判 B2/B3 GAP；该报告可作为“入口文档缺少 closure 摘要”的提示，但不能作为 B2/B3 实质状态的主要依据。

### E-H1: Economy 单事实源需要清理派生示例
经济风险：权威公式已存在，但派生示例和说明仍有旧数值；必须同步所有用户可见示例。

### X-H1: API/DX 参考命令仍展示 `body_cost × 0.5`
DX 风险：SDK/API 用户最可能阅读 `commands.md`，固定 50% 示例会直接传播错误实现。

### T-H1: Deterministic replay 对 Recycle refund 仍有歧义
确定性风险：同一命令在不同实现中可能按固定 50% 或 lifespan formula 结算，Replay 合同不闭包。

## Medium/Low 处置

| ID | 问题 | 来源方向 | 处置 |
|----|------|---------|------|
| M1 | `design/README.md` 未暴露 B2/B3 closure 入口证据 | GPT Performance / GPT Designer | Medium：建议补充导航链接，但不是 B2/B3 blocker 根因 |
| M2 | DeepSeek 多报告未检查派生文档残留 | Speaker 复核 | Low：记录为审查覆盖偏差；不影响其对权威公式已存在的正面证据 |
| M3 | B3 在 design 层没有 S14 明确引用 | GPT Designer | Low：B3 权威属于 core/system manifest；可在 design 文档加引用改善可发现性，但不阻塞 |
| M4 | `Resource Ledger §6` 与实际 §2.5/§Empire Upkeep 命名混用 | Economy/Designer 报告间接暴露 | Medium：修复 B2 时顺带统一章节引用，避免新一轮误判 |

## D-items（需用户裁决）

无必须用户裁决项。R25 的阻塞项均为文档一致性修复，可直接按权威公式收敛。

## 文档维护项

- 更新 `specs/core/02-command-validation.md`：清理 §3.9 与 §10.3 的 Recycle 固定 50% 文本，统一引用 §3.18 / Resource Ledger / API Registry。
- 更新 `specs/reference/commands.md`：Recycle 示例改为 lifespan-proportional 10%–50%。
- 更新 `design/gameplay.md`：Drone 身体规划、经济分类账、帝国维护费示例效果改为当前权威公式/派生值；删除“待 B6 闭合”过期语句。
- 检查 `design/economy-balance-sheet.md` 中 `Resource Ledger §6` 等章节名引用是否与当前 `08-resource-ledger.md` 实际章节一致。
- 修复后建议启动 R26 Closure Verification，仅验证 B2 残留；B3 可抽样确认但不应再作为主要阻塞。

## 评审统计

### 7×2 verdict/severity 矩阵

| Direction | GPT-5.5 | DeepSeek V4 Pro | Speaker 权重说明 |
|-----------|---------|-----------------|------------------|
| Architect | REJECT / B2 GAP, B3 CLOSED | APPROVE / B2 CLOSED, B3 CLOSED | GPT 指出 `02-command-validation.md` 同文件冲突，证据成立 |
| Security | REJECT / B2 GAP, B3 CLOSED | APPROVE / B2 CLOSED, B3 CLOSED | GPT 指出 §3.9/§3.18/§10.3 多口径，证据成立 |
| Designer | REJECT / B2 GAP, B3 GAP | APPROVE / B2 CLOSED, B3 CLOSED | B2 残留成立；B3 GAP 降权为读取范围不足 |
| Performance | REJECT / B2 GAP, B3 GAP | APPROVE / B2 CLOSED, B3 CLOSED | GPT 仅 README 范围，实质权重低；不作为 B3 blocker |
| Economy | REJECT / B2 GAP, B3 CLOSED | APPROVE / B2 CLOSED, B3 CLOSED | GPT upkeep 旧示例证据成立 |
| API/DX | REJECT / B2 GAP, B3 CLOSED | APPROVE / B2 CLOSED, B3 CLOSED | GPT `commands.md` 固定 50% 证据成立 |
| Determinism | REJECT / B2 GAP, B3 CLOSED | APPROVE / B2 CLOSED, B3 CLOSED | GPT Recycle replay 歧义证据成立 |

### 共识强度评估

- B2=GAP：High。跨方向（Architect/Security/Designer/Economy/API-DX/Determinism）与至少一个模型族重复发现，并经 Speaker 文件复核确认。
- B3=CLOSED：High。权威链和唯一 writer contract 均已在 core manifest 中明确；少数 GAP 判定来自读取范围不足而非冲突证据。
- 总体 Verdict：REQUEST_MAJOR_CHANGES。原因是 Closure Verification 的通过条件要求 B2/B3 全部 CLOSED，而 B2 仍有 Blocking GAP。
