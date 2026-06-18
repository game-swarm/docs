# Swarm 设计评审 R20 — Speaker 共识报告

## 裁决概要

R20 是 R19 后的 closure verification 轮，不重新评审设计本身，只验证 R19 六项 Blocker 与四项用户裁决是否在权威文档链路中闭合。

- Phase 模式：Closure Verification，全量/编号项验证回退模式；不启用 Plan B CrossCheck Phase 2。
- 评审完成情况：14/14 reviewers 完成。
- 总体收敛：IDL YAML 与 `api-registry.md` 权威链路已基本闭合；派生设计/参考文档仍存在多处传播残留。
- Freeze 状态：**NOT FROZEN**。原因不是权威 IDL 主源失败，而是面向实现者/SDK/规则作者的派生文档仍会给出冲突口径。

## 总体 Verdict

**CONDITIONAL_APPROVE / NOT FROZEN**

理由：14 份评审中 10 份为 APPROVE，4 份为 CONDITIONAL_APPROVE。所有评审均承认 R19 的核心权威源修复已经落地：`game_api.idl.yaml`、`auth_api.idl.yaml`、`economy.idl.yaml` 与 `api-registry.md` 建立了三 IDL 源与统一 Registry 链路。但 GPT API/DX、GPT Designer、GPT Economy、DSV4 Economy 共同指出派生文档残留仍可误导实现，因此不能宣布冻结。

## 逐项闭合汇总

| 项 | Speaker 判定 | 证据共识 | 残留 |
|----|--------------|----------|------|
| B19-1 RejectionReason canonical 传播 | **CLOSED_WITH_PROPAGATION_GAP** | 多数评审确认 Registry 合并为 47 canonical codes，`debug_detail` 非 canonical | `design/interface.md` 仍写 35 变体，并保留旧 SwarmError envelope 示例 |
| B19-2 MCP/Auth tool namespace 收敛 | **CLOSED_WITH_PROPAGATION_GAP** | Auth API 独立源与 11 个 auth tools 已在 Registry 呈现 | `design/interface.md` 仍列旧/phantom tools，如 `swarm_get_schema`、`swarm_submit_csr`、`swarm_token_refresh` 等 |
| B19-3 deploy replay_class → deploy_mutation | **CLOSED_WITH_PROPAGATION_GAP** | IDL 与 Registry 均为 `deploy_mutation`，并有 `fdb_version_counter` 机制 | `design/interface.md` MCP 分类表仍写 `idempotent_mutation` |
| B19-4 IDL f64 → fixed-point | **CLOSED** | 8 类 fixed-point type 在 Registry 汇总；活跃 IDL 字段无 f64 | 仅剩说明性历史文字，不构成 blocker |
| B19-5 worker_pool 256 + hard_cap 1000 | **CLOSED** | IDL、Registry、engine 容量推导一致 | 无阻断残留 |
| B19-6 economy.idl.yaml 机器源 | **CLOSED_WITH_ECONOMY_DERIVED_GAP** | `economy.idl.yaml` 独立，Registry §10 汇总 7 operations 与 fixed-point 经济公式 | Resource Ledger / Economy Balance Sheet 仍有权威源与参数口径冲突 |
| U1/A auth_api.idl.yaml 独立 | **CLOSED** | Auth API 独立版本、独立工具、独立 RejectionReason namespace | 部分评审因白名单只通过 Registry 间接验证，但不改变结论 |
| U2/B economy.idl.yaml 独立 | **CLOSED** | Economy IDL 独立版本、类型、operations、limits | 经济派生文档需降级为引用 IDL/Registry |
| U3/A worker_pool default 256 + hard_cap 1000 | **CLOSED** | 256 runtime default / 1000 compile-time hard cap 一致 | 无 |
| U4/A deploy_mutation replay_class | **CLOSED_WITH_PROPAGATION_GAP** | 权威源已闭合为 `deploy_mutation` | `design/interface.md` 仍残留旧 replay_class |

## 共识 Blocker

R20 不再发现新的“权威源级”共识 Blocker；但存在一个冻结前必须清理的共识级传播残留包。

### B20-1: 派生文档传播残留阻止 Freeze

**方向 × 模型矩阵**：
- API/DX × GPT：明确列出 `design/interface.md`、`commands.md`、`host-functions.md` 残留，Verdict CONDITIONAL_APPROVE。
- API/DX × DeepSeek：指出 `design/interface.md` 的 `swarm_deploy` replay_class 残留，Verdict CONDITIONAL_APPROVE。
- Designer × GPT：指出 `design/interface.md` 的 RejectionReason 35 变体与 `swarm_deploy` 旧 replay_class，Verdict CONDITIONAL_APPROVE。
- Economy × GPT：指出 Resource Ledger / Economy Balance Sheet 仍继承旧经济权威源与参数冲突，Verdict CONDITIONAL_APPROVE。
- Economy × DeepSeek：指出 StorageTax tier 定义在 economy IDL 与设计文档间不一致，Verdict CONDITIONAL_APPROVE。

**问题**：权威 IDL/Registry 已收敛，但派生文档仍重新声明旧表格、旧 replay_class、旧 error envelope、旧 auth/MCP tools、旧经济公式权威源。这会导致实现者绕开 Registry 读取 Markdown 时产生分叉。

**修正要求**：
1. `design/interface.md` 必须改为引用 `api-registry.md`，不得重新声明可冲突的 MCP tools / replay_class / error envelope 表。
2. `swarm_deploy` 所有可见文档必须统一为 `deploy_mutation`。
3. RejectionReason 文本必须统一为 47 canonical codes + `debug_detail` 非 canonical；删除或改写 35 变体残留。
4. Auth/MCP 工具名必须与 `auth_api.idl.yaml` / `api-registry.md` 对齐；删除 `swarm_get_schema`、`swarm_get_docs`、`swarm_submit_csr`、`swarm_token_refresh`、`swarm_change_password`、`swarm_federated_login` 等不属于当前 Registry 的接口表项，或明确标为旧设计/已移除。
5. Resource Ledger 与 Economy Balance Sheet 必须降级为引用 `economy.idl.yaml` / `api-registry.md`，并统一 StorageTax / AlliedTransfer 参数口径。
6. 修复后应执行一次全文 stale-reference scan，而不是只改单行。

## CrossCheck 补漏发现（基于 Phase 2）

无 Phase 2 补漏发现。本轮为 closure verification 回退模式，评审员按编号项验证，输出不包含 CrossCheck 章节，也不创建 Phase 2 补充任务。

## 方向专属 High 优先级

### X-H1: API/DX 派生接口文档未完全重生成

**来源**：rev-gpt-apidx、rev-dsv4-apidx

`design/interface.md`、`commands.md`、`host-functions.md` 中仍存在旧接口或概念签名。API/DX 方向认为这会直接影响 SDK/MCP 调用方理解，必须在 Freeze 前清理。

### D-H1: 设计文档仍暴露旧 RejectionReason / deploy 口径

**来源**：rev-gpt-designer

`design/interface.md` 仍写 “35 变体” 与 `swarm_deploy = idempotent_mutation`。虽然 Registry 是权威，但设计文档面向读者，不能长期保留冲突表格。

### E-H1: 经济派生文档与 economy IDL 权威源冲突

**来源**：rev-gpt-economy、rev-dsv4-economy

Resource Ledger 与 Economy Balance Sheet 对公式权威源、StorageTax tier、AlliedTransfer 参数仍有冲突。经济方向两模型均给出 CONDITIONAL_APPROVE，因此这是方向内强共识 High。

## Medium/Low 处置

| ID | 问题 | 来源方向 | 处置 |
|----|------|----------|------|
| M20-1 | 部分评审因白名单未能直接读取 `auth_api.idl.yaml` 或 `economy.idl.yaml` | Architect/Security/API/DX | 记录为验证范围限制；Registry 证据足以支持独立源闭合 |
| M20-2 | `design/architecture.md` 白名单路径缺失 | Determinism GPT | 非阻断；本轮按 IDL/Registry 权威源验证 |
| M20-3 | `02-command-validation.md` 旧示例文字（如 Recycle 固定退还） | Performance GPT | 非阻断文档清理项，纳入 stale-reference scan |
| M20-4 | `01-tick-protocol.md` EXECUTE timeout 示意与预算表软截止语义差异 | Performance GPT | 非 R20 目标项；后续规范清理 |
| M20-5 | game_api 与 auth_api 同名 RejectionReason 通过 namespace/layer 区分 | Security DSV4 | Informational，不需要修改 |

## D-items（需用户裁决）

本轮无新的用户裁决项。R19 用户裁决闭合状态：

- U1/A：auth_api.idl.yaml 独立 — CLOSED。
- U2/B：economy.idl.yaml 独立 — CLOSED。
- U3/A：worker_pool default 256 + hard_cap 1000 — CLOSED。
- U4/A：deploy_mutation replay_class — CLOSED_WITH_PROPAGATION_GAP。

## 文档维护项

1. 以 `api-registry.md` 为权威，重写或删减 `design/interface.md` 中会重新声明 MCP tools、Replay Class、Error Envelope、RejectionReason 计数的表格。
2. 以 `economy.idl.yaml` / Registry §10 为权威，更新 Resource Ledger 与 Economy Balance Sheet 的 StorageTax / AlliedTransfer / 公式权威源说明。
3. 对以下关键词进行全仓扫描并清理或标注历史：`idempotent_mutation` + `swarm_deploy`、`35 变体`、`code: -32000`、`swarm_error`、`retry_allowed`、`idempotency_key`、`swarm_get_schema`、`swarm_submit_csr`、`swarm_token_refresh`、`swarm_change_password`、`swarm_federated_login`、`CommandAction::Custom`、`CustomActionRegistry`。
4. 修复后生成 R21 closure verification，重点只验证 B20-1 派生文档残留包是否清零。

## R15 → R20 收敛评估

| 轮次 | Speaker 结论 | 收敛状态 |
|------|--------------|----------|
| R15 | REQUEST_MAJOR_CHANGES | 建立大量共识 Blocker，核心问题是文档/IDL/接口契约分裂 |
| R16 | REQUEST_MAJOR_CHANGES | CrossCheck 增多，确认 API、Security、Economy、Determinism 多方向互相牵连 |
| R17 | REQUEST_MAJOR_CHANGES | 生成式单源与 IDL/Registry 收束开始成形，但传播链未闭合 |
| R18 | REQUEST_MAJOR_CHANGES | 多个 D-items 需要用户裁决；权威源选择尚未完全统一 |
| R19 | REQUEST_MAJOR_CHANGES / NOT FROZEN | 六项传播残留 Blocker 明确化，用户裁决 U1–U4 给出方向 |
| R20 | CONDITIONAL_APPROVE / NOT FROZEN | 权威 IDL/Registry 主链路基本闭合；剩余问题转为派生文档 stale-reference 清理 |

R20 的重要进展是：问题性质从“设计/契约源头未定”降级为“派生文档传播残留”。这说明 R15→R20 已显著收敛，但 Freeze 的最后门槛是所有读者可见文档不得给出冲突实现口径。

## 评审统计

### Verdict Matrix

| Direction | GPT-5.5 | DeepSeek V4 Pro | 方向结论 |
|-----------|---------|-----------------|----------|
| Architect | APPROVE | APPROVE | CLOSED |
| Security | APPROVE | APPROVE | CLOSED |
| Designer | CONDITIONAL_APPROVE | APPROVE | 派生设计文档残留 |
| Performance | APPROVE | APPROVE | CLOSED |
| Economy | CONDITIONAL_APPROVE | CONDITIONAL_APPROVE | 经济派生文档残留 |
| API/DX | CONDITIONAL_APPROVE | CONDITIONAL_APPROVE | 接口派生文档残留 |
| Determinism | APPROVE | APPROVE | CLOSED |

### 数量统计

- APPROVE：10/14
- CONDITIONAL_APPROVE：4/14
- REQUEST_MAJOR_CHANGES：0/14
- REJECT：0/14
- R19 Blocker 权威源闭合：6/6
- 用户裁决权威源闭合：4/4
- 冻结阻断残留包：1 个（B20-1 派生文档传播残留）

### 共识强度

- 权威 IDL/Registry 已闭合：强共识（14/14 无人反对）。
- 派生文档仍有残留：中强共识（5/14 明确指出，覆盖 API/DX、Designer、Economy 三方向；其中 API/DX 与 Economy 是方向内双模型共识）。
- 是否足以阻止 Freeze：Speaker 判定为是。因为 Freeze 面向实现阶段，读者不能被派生文档旧表格误导。

## 最终裁决

**CONDITIONAL_APPROVE / NOT FROZEN**

进入 R21 的条件：完成 B20-1 文档维护项，并由下一轮 closure verification 验证派生文档残留清零。若 R21 仅剩白名单/历史说明类非阻断项，Speaker 可宣布 FROZEN。
