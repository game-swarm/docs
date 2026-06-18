# Swarm 设计评审 R21 — Speaker 目标验证裁决

生成时间：2026-06-18 16:18:29 CST  
Speaker：rev-speaker

## 裁决概要

R21 是 R20 后的目标验证轮（Closure Verification），不执行两级阅读/14 人全量议会；本轮只验证单一目标：

- **B20-1**：`design/interface.md` 派生文档传播残留清零。

本轮共收到 3 份目标验证评审：

| Reviewer | 文件 | Verdict |
|---|---|---|
| API/DX | `/data/swarm/docs/reviews/R21/rev-apidx.md` | CLOSED |
| Designer | `/data/swarm/docs/reviews/R21/rev-designer.md` | CLOSED |
| Economy | `/data/swarm/docs/reviews/R21/rev-economy.md` | CLOSED |

Speaker 复核了 3 份评审原文，并对目标文档做轻量抽样核验。3/3 评审均确认 B20-1 四个残留点全部清零；Speaker 未发现与评审结论冲突的证据。

## 总体 Verdict

**FROZEN**

理由：R20 唯一残留目标 B20-1 已由 3 个独立方向验证为 CLOSED，且四个检查点均有一致证据支撑。当前没有剩余 Blocker、High、D-item 或需要继续进入 R22 的残留项。

## B20-1 验证结论

### B20-1.1：旧 MCP 工具完整表传播残留

**结论**：CLOSED

**共识证据**：

- API/DX：`interface.md` §4.1 已替换为概念分类概述，并明确“不列完整表”，canonical schema 以 `api-registry.md` §3 为准。
- Designer：确认 `design/interface.md` 只保留 high-level conceptual narrative，canonical detail 已委托给 `api-registry.md`。
- Economy：确认 §4.1 是 concept overview + registry pointer，而非完整工具表。
- Speaker 抽样：`/data/swarm/docs/design/interface.md:21` 明确“不列完整表”，并声明 canonical schema、replay_class、rate_limit、security columns 以 Registry 为准。

### B20-1.2：`swarm_deploy` replay_class 残留

**结论**：CLOSED

**共识证据**：

- API/DX：确认 `interface.md` L158 标注 `replay_class: deploy_mutation`。
- Designer：确认 `interface.md:158` 与 `api-registry.md:277` 一致。
- Economy：确认 `swarm_deploy` 使用 `deploy_mutation`，并与 registry §3.2 Deploy row 一致。
- Speaker 抽样：`/data/swarm/docs/design/interface.md:158` 与 `/data/swarm/docs/specs/reference/api-registry.md:277` 均为 `deploy_mutation`。

### B20-1.3：`RejectionReason` 旧 35 变体计数残留

**结论**：CLOSED

**共识证据**：

- API/DX：确认 `interface.md` L118 引用 `api-registry.md` §2 的 47 canonical codes（35 game + 12 auth）。
- Designer：确认 `interface.md:118` 与 `api-registry.md` §2 对齐。
- Economy：确认 `interface.md` L118 为 47 canonical codes。
- Speaker 抽样：`/data/swarm/docs/design/interface.md:118` 明确写入 “47 canonical codes (35 game + 12 auth)”。

### B20-1.4：五个 phantom tools 残留

**结论**：CLOSED

**检查对象**：

- `swarm_get_schema`
- `swarm_submit_csr`
- `swarm_token_refresh`
- `swarm_change_password`
- `swarm_federated_login`

**共识证据**：

- API/DX：确认五个 phantom tools 只在 `interface.md` L33 的“已移除的工具”声明中出现，概念表和 `api-registry.md` 全文无残留。
- Designer：确认五个 phantom tools 均不在 `api-registry.md` authority tables 中，仅作为 removed tools 出现在 `interface.md:33`。
- Economy：确认五个 phantom tools absent from authority table / canonical registry。
- Speaker 抽样：`/data/swarm/docs/design/interface.md:33` 仅以“已移除的工具”形式列出；`/data/swarm/docs/specs/reference/api-registry.md` 对五个 phantom names 无命中。

## R15 → R21 收敛总结

注：当前工作区可见的本地评审文件只有 R21 三份目标验证报告；R15→R20 的收敛脉络依据看板任务历史摘要与父任务 handoff，而非本地逐轮 verdict 原文。

| 轮次 | 收敛状态 | Speaker 观察 |
|---|---|---|
| R15 | 主链路形成 | YAML → `api-registry.md` 主链路开始成为 canonical source，但派生文档传播仍未完全闭合。 |
| R16 | 主要一致性问题暴露 | 出现多项共识 Blocker，集中在 API/security/interface/reference 多文档一致性。 |
| R17 | Blocker 聚类稳定 | 继续聚合跨方向 blocker 与 CrossCheck，问题从架构方向收敛到文档传播和 registry 权威性。 |
| R18 | 主链路基本闭合 | YAML → `api-registry.md` 主链路基本闭合，但 API/安全/派生文档仍有残留传播风险。 |
| R19 | 残留项减少但未冻结 | Speaker verdict 为 REQUEST_MAJOR_CHANGES / NOT FROZEN，仍有明确残留 blocker。 |
| R20 | 进入单点残留状态 | 14/14 综合后为 CONDITIONAL_APPROVE / NOT FROZEN，剩余自动向 R21 传递的目标为 B20-1。 |
| R21 | 目标验证清零 | 3/3 目标验证评审均 CLOSED；B20-1 四个传播残留点清零，达到 FROZEN。 |

收敛模式从“多方向结构性 blocker”逐步压缩为“单一派生文档传播残留”，最终在 R21 被 3 个方向独立关闭。该模式符合冻结前 Closure Verification：不重新开启全量设计争论，只验证上一轮明确传递的编号项是否归零。

## 共识 Blocker

无。

B20-1 不再是 blocker；它在 R21 中被 3/3 评审关闭。

## CrossCheck 补漏发现

无。

R21 是 Closure Verification 回退模式，不执行 Phase 1 CrossCheck → Phase 2 补漏流程；本轮报告也未提出新的外溢方向问题。

## 方向专属 High 优先级

无。

API/DX、Designer、Economy 三个方向均未提出新的 High 或 Critical 项。

## Medium/Low 处置

| ID | 问题 | 来源方向 | 处置 |
|---|---|---|---|
| — | 无 Medium/Low 残留 | — | 无需处置 |

## D-items（需用户裁决）

无。

R21 未产生需要用户裁决的设计分歧。

## Freeze 后维护指引

既然 R21 判定为 **FROZEN**，后续维护应按以下规则执行：

1. **保持 single-source-of-truth**：MCP 工具 canonical schema、rate limit、security columns、`replay_class` 继续以 `/data/swarm/docs/specs/reference/api-registry.md` 为准；`design/interface.md` 只保留概念说明与指针。
2. **禁止派生表复刻**：不要在 `design/interface.md` 或其他 narrative 文档重新复制完整 MCP tool table；如需新增工具，先改 Registry，再在 narrative 文档增加概念级描述。
3. **新增/移除工具需双向扫描**：每次变更 MCP 工具名后，全文扫描 phantom/stale names，尤其是 removed tools、diagram、example、appendix、ROADMAP 条目。
4. **`RejectionReason` 数量变更需同步声明**：若 canonical codes 从 47 变更，必须同时更新 registry、IDL、interface narrative 中的数量说明，避免再次出现旧计数传播。
5. **`deploy_mutation` 作为部署语义冻结点**：`swarm_deploy` 不应回退到旧 replay classification；若部署机制变更，应通过新的 review item 明确解冻。
6. **后续评审默认 post-freeze regression check**：除非用户要求全量设计评审，后续轮次应聚焦新增改动是否破坏 FROZEN 状态，而不是重新评估已关闭的 B20-1。

## 若 NOT FROZEN 的残留项

不适用。

R21 判定为 FROZEN，因此没有需传递到 R22 的残留项。

## 评审统计

### Verdict 矩阵

| Direction | Reviewer 文件 | Verdict | B20-1.1 | B20-1.2 | B20-1.3 | B20-1.4 |
|---|---|---|---|---|---|---|
| API/DX | `rev-apidx.md` | CLOSED | CLOSED | CLOSED | CLOSED | CLOSED |
| Designer | `rev-designer.md` | CLOSED | CLOSED | CLOSED | CLOSED | CLOSED |
| Economy | `rev-economy.md` | CLOSED | CLOSED | CLOSED | CLOSED | CLOSED |

### 共识强度评估

- **方向覆盖**：3/3
- **目标检查点覆盖**：4/4
- **关闭一致性**：3/3 reviewers 全部 CLOSED
- **反例/分歧**：0
- **Speaker 抽样冲突**：0

结论：B20-1 关闭信号强，足以支持 R21 FROZEN。