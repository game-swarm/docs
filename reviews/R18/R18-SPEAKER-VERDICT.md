# Swarm 设计评审 R18 — Speaker 共识报告

## 裁决概要

- 本轮性质：R18 Phase 1 clean-slate 评审，重点验证 `game_api.idl.yaml` → Markdown 的生成式单事实源是否真正闭合。
- Phase 1 完成情况：14/14 reviewers 完成，7 个方向 × 2 个模型均有报告。
- Phase 2 补漏情况：本任务未等待/启动 Phase 2 补充评审；各报告的 CrossCheck 已直接纳入本裁决的 Blocker 与 High 项。无独立 Phase 2 补漏报告。
- 收敛评估：评审高度收敛。多数评审员同意：`game_api.idl.yaml` 与 `specs/reference/api-registry.md` 的直接生成链路基本闭合；但“YAML/API Registry → 所有开发者会阅读和实现的 Markdown 文档”没有闭合。大量手写 reference/spec/design 文档仍重复声明 API enum、MCP tools、Host Function、replay class、安全列、容量常量、经济公式和 tick/replay 语义。
- Freeze 状态：不得冻结。当前状态适合进入“单源闭合修复 / 文档生成化改造”迭代，不适合进入实现。

## 总体 Verdict

REQUEST_MAJOR_CHANGES

理由：9/14 reviewers 给出 `REQUEST_MAJOR_CHANGES`，1/14 给出 `REQUEST_CHANGES`，4/14 给出 `CONDITIONAL_APPROVE`。没有任何 reviewer 给出无条件 APPROVE。跨方向、跨模型均确认：YAML → `api-registry.md` 主链路已改善，但单事实源闭合范围不足，开发者实际会读的 Markdown 文档仍能生成不同 SDK、不同校验器、不同 replay/security 行为。

## 共识 Blocker（跨方向 + 跨模型同意）

### B1: “YAML → api-registry.md”闭合，不等于“API 合同全域闭合”

**方向 × 模型矩阵**:
- Architect: rev-gpt-architect A1/A3/A6/A7, rev-dsv4-architect CrossCheck/C3/H2/M3
- API/DX: rev-gpt-apidx C1/C2/C3/H1/H3, rev-dsv4-apidx C1-C5/H1-H4
- Designer: rev-gpt-designer G1/G2/G3, rev-dsv4-designer C1
- Security: rev-gpt-security H1/H2/H4, rev-dsv4-security C1/C2/H1/H3
- Determinism: rev-gpt-determinism T1/T5, rev-dsv4-determinism D4/D5
- Economy: rev-gpt-economy E1/E7, rev-dsv4-economy D3/D5
- Performance: rev-gpt-performance P1, rev-dsv4-performance D1/D3

**问题**: 多数评审员独立确认 `game_api.idl.yaml` 与 `api-registry.md` 在主干数量上基本一致：CommandAction 19、RejectionReason 35、active MCP tools 46、Host Functions 5、TickTrace 22 等。问题在于其他 Markdown 文档仍手写并重复声明同一合同，包括 `commands.md`、`mcp-tools.md`、`host-functions.md`、`02-command-validation.md`、`08-api-idl.md`、`interface.md`、`auth.md`、`engine.md` 等。当前单源只覆盖 registry，不覆盖实现者和 SDK 作者实际会引用的文档面。

**修正要求**:
- 明确定义“唯一权威源”的覆盖范围：至少覆盖 API enum、CommandAction 参数、RejectionReason、MCP tool schema/security columns、Host Function ABI、limits、replay_class、TickTrace envelope。
- 将重复声明的 Markdown 表格改为以下二选一：由 YAML 生成；或删除表格，改为指向 `api-registry.md` 的引用摘要。
- 为所有派生文档加入生成来源/provenance：source YAML path、source commit/hash、generator version、generated_at。
- CI 增加 drift gate：任一 Markdown 中出现可生成 API 枚举/签名/常量但未标注 generated 或 superseded 时失败。

### B2: RejectionReason canonical enum 与旧调试细节仍混用

**方向 × 模型矩阵**:
- Architect: rev-gpt-architect A1, rev-dsv4-architect CrossCheck
- API/DX: rev-gpt-apidx C3, rev-dsv4-apidx C1/C2
- Designer: rev-gpt-designer G2, rev-dsv4-designer C1
- Determinism: rev-gpt-determinism T1, rev-dsv4-determinism D6/D5 related
- Economy: rev-dsv4-economy D5

**问题**: YAML/registry 的 35 个 canonical RejectionReason 已基本一致，但 `commands.md`、`02-command-validation.md`、`08-api-idl.md` 等仍出现 `NotMovable`、`Fatigued`、`MissingBodyPart`、`TileBlocked`、`CarryFull`、`AlreadyHacked`、`InvalidDamageType` 等旧 variant 或带数据字段的 variant。这些在 D2/B 设计下应进入 `debug_detail`，不应成为 wire enum。若不同实现分别读取 YAML 与手写 Markdown，会导致 SDK 类型、错误处理、TickTrace/replay 校验和命令校验器分叉。

**修正要求**:
- 删除或 supersede `08-api-idl.md` 中旧 RejectionReason enum 和旧 CommandAction 示例。
- `commands.md` 与 `02-command-validation.md` 不再列 wire-level 非 canonical code；逐指令矩阵应写“canonical code + debug_detail 示例”。
- 建立从旧上下文原因到 canonical code 的生成映射表，例如 `MissingBodyPart: Work` → `NotEnoughBodyParts` + `debug_detail`。
- 在 TickTrace/SwarmError 中明确：wire enum 只能是 35 canonical code；pipeline-only 错误与 debug_detail 不进入 enum。

### B3: MCP/Auth/Replay security columns 未纳入同一个机器源

**方向 × 模型矩阵**:
- Security: rev-gpt-security H1/H2/H3/H4, rev-dsv4-security C1/C2/H1/H2/H3
- API/DX: rev-gpt-apidx C2/H2, rev-dsv4-apidx C4/H2
- Architect: rev-gpt-architect A3/A4, rev-dsv4-architect deploy/replay CrossCheck non-issue + security drift noted by dsv4-security
- Designer/Economy: rev-gpt-designer G1, rev-gpt-economy E7

**问题**: 账号注册、CSR、证书续签/吊销、passkey、密码恢复、账号删除/恢复、federated login 等安全关键工具在 `auth.md` 中存在，但未完整进入 YAML/API Registry；`swarm_deploy` 在 YAML tool 表中仍可被解释为 `idempotent_mutation`，而 `auth.md`/command-source 语义要求 `deploy_mutation` + FDB version_counter；auth replay class 词汇、rate limit、audience 格式、WebSocket 每消息签名语义也不闭合。安全列若散落在 prose 中，codegen/CI 无法强制 `required_scope`、`replay_class`、`rate_limit_key`、`visibility_filter` 和 nonce/crash semantics。

**修正要求**:
- 用户需裁决 auth 工具放入 `game_api.idl.yaml` 还是独立 `auth_api.idl.yaml`；但无论哪种，必须机器可读并参与同一 drift gate。
- 将 `replay_class` 定义为机器枚举，并为每个值声明 `nonce_mechanism`、`idempotency_key`、`crash_semantics`、`rate_limit_key`、`requires_fdb_counter`。
- 明确 `swarm_deploy` 的 replay class：若采用 `deploy_mutation`，则 YAML/registry/tool schema 必须直接写 `deploy_mutation`，不得只在 prose 里说明。
- 统一 WebSocket 安全合同：握手后免签 vs 每消息 seq+MAC 只能保留一种，或按 transport/capability profile 明确分层。

### B4: Host Function ABI、基础类型与 error schema 仍不完全生成化

**方向 × 模型矩阵**:
- API/DX: rev-gpt-apidx H1, rev-dsv4-apidx C3/T1/T2/T3/E1/E2/E3/H4
- Architect: rev-gpt-architect A3, rev-dsv4-architect generated closure verification + external drift
- Performance: rev-gpt-performance host/fuel concerns, rev-dsv4-performance D4
- Determinism: rev-gpt-determinism T6, rev-dsv4-determinism D1

**问题**: `api-registry.md` 与 YAML 的 Host Functions 主列表基本一致，但 `host-functions.md` 等手写文档仍有旧签名/预算模型；YAML 引用了 `EntityId`、`ResourceType`、`StructureType`、`DamageType` 等基础类型却未形成完整 type closure；46 个 MCP tools 的 per-tool error schema/SwarmError envelope 建模仍不足。结果是 SDK/ABI 生成器无法只靠机器源生成完整绑定和错误处理。

**修正要求**:
- 将 `host-functions.md` 改为 YAML 生成，或降级为非权威说明并链接 registry。
- 在 YAML 中补齐基础类型定义、复合类型展开规则、error schema、SwarmError envelope、retry_allowed/debug_detail 字段。
- Host Function fuel budget、调用上限、error priority 与 ABI 签名必须来自同一机器源。

### B5: 容量/性能常量仍有手写权威值分叉

**方向 × 模型矩阵**:
- Performance: rev-gpt-performance P1, rev-dsv4-performance D1/D2/D3
- Architect: rev-gpt-architect A6, rev-dsv4-architect C3/H2
- Determinism: rev-gpt-determinism T5, rev-dsv4-determinism D4/D5

**问题**: 多个容量和性能关键常量仍在 YAML/registry 与手写文档间冲突：worker pool `256` vs engine `MAX_POOL = 1000`；per-player drone cap `500` vs command-validation `50`；WASM output 256KB 截断 vs 整批丢弃；FDB transaction size 10KB vs 10MB；WASM module/blob size、EXECUTE deadline、CPU/fuel/cgroup 模型也存在不同层级的合同不一致。这些不只是文案问题，会影响性能预算、admission control、parallel execution、timeout 行为和 replay 可重复性。

**修正要求**:
- 所有 capacity/performance limits 只从 YAML/registry 生成；`engine.md` 只能引用，不得硬编码不同数字。
- 修正 `engine.md` 的 worker pool 推导：如果权威值是 256，则容量推导必须重算；如果目标仍是 1000，则 YAML/registry 必须更新并给出硬件预算。
- 统一 WASM output 超限语义、module/blob size、FDB transaction upper bound，并加入 CI 检查。
- 给出 100k command / 500 player / 400ms tick budget 的 microbenchmark 入场指标。

### B6: Tick/replay/determinism 合同仍存在跨文档冲突

**方向 × 模型矩阵**:
- Determinism: rev-gpt-determinism T2/T3/T4/T6, rev-dsv4-determinism D1/D3/D6/D7
- Architect: rev-gpt-architect A2/A4/A5, rev-dsv4-architect C1/C2/H3/H4
- Performance: rev-gpt-performance P2, rev-dsv4-performance D3/D5
- Security: rev-gpt-security M4, rev-dsv4-security replay_class concerns

**问题**: `status_advance_system` 调度位置在 `02-command-validation.md` 与 `06-phase2b-system-manifest.md` 冲突；TickTrace `terminal_state` 兼具 WASM 终止状态和 tick commit/audit 状态两种语义；TickTrace/replay 完整性在 tick protocol 的“同事务强一致”与 persistence contract 的“FDB commit 成功、blob 可异步失败”之间冲突；YAML/API 暴露多处 `f64` 且标为 replay-safe；custom_actions 排序、SIMD 开关、snapshot truncation/output truncation 也有边界未闭合。

**修正要求**:
- `06-phase2b-system-manifest.md` 成为唯一调度权威；其他文档删除 inline schedule 或改为引用。
- 拆分 `terminal_state`：至少区分 `wasm_terminal_state` 与 `tick_commit/audit_upload_state`。
- 选择 TickTrace 持久化模型：强一致失败即放弃 tick，或 FDB-first + audit_gap；两者不能同时保留。
- replay-safe API 不得输出平台相关 `f64`；改为定点/整数/basis points，或将这些字段明确标为 display-only 且排除 replay compare。
- 为 custom_actions 排序、SIMD feature 记录、seed epoch 边界写入确定性合同。

### B7: 经济机器事实源没有闭合到 Resource Ledger / Balance / YAML

**方向 × 模型矩阵**:
- Economy: rev-gpt-economy E1/E2/E3/E4/E5/E6/E7, rev-dsv4-economy D1/D2/D4/D6/D7/D8
- Determinism: rev-dsv4-determinism D2, rev-gpt-determinism refund/replay related
- Architect: rev-dsv4-architect H1, rev-gpt-architect A6 related
- Designer: rev-dsv4-designer C1/H1, rev-gpt-designer G5

**问题**: 经济层的“单事实源”仍与 API 单事实源脱节。`Resource Ledger` 声称资源流动由统一 ResourceOperation/Transfer Gateway 结算，但 YAML/API Registry 的 `resource_operation` 只覆盖部分 CommandAction，未覆盖 Upkeep、StorageTax、PvEAward、RecycleRefund、BuildCost、SpawnCost、AlliedTransfer 等关键操作。Recycle refund、storage_tax、empire upkeep、allied transfer、tutorial refund、PvE faucet 等仍有公式/口径/示例冲突。

**修正要求**:
- 建立经济机器源：可扩展 YAML 的 `resource_operation`，或新建 `resource_ledger.idl.yaml`，但必须生成 Resource Ledger、TickTrace resource schema、economy dashboard schema。
- 统一 Recycle refund：flat 50%、lifespan proportional 10%-50%、tutorial 100% 三者的适用条件只能保留一套权威表达。
- 修正 storage tax 量纲与数值表，确保公式能导出示例。
- 统一 empire upkeep O(n²) 目标与 Rhai mod 默认参数；若默认近线性，应明确这不是反雪球主机制。

## CrossCheck 补漏发现（基于 Phase 2）

无 Phase 2 补漏发现。本轮未产生独立 Phase 2 报告。Phase 1 CrossCheck 的主要结论如下，已并入上方 Blocker：

### CX1: YAML ↔ api-registry.md 直接链路基本闭合，但外层 Markdown 漂移
**来源**: rev-dsv4-architect, rev-dsv4-determinism, rev-dsv4-performance, rev-gpt-determinism, rev-gpt-performance 等  
**发现**: 多名评审员核对到 YAML 与 `api-registry.md` 的核心计数一致；漂移主要发生在 `api-registry.md` 之外的手写文档。  
**处置**: 升级为 B1。

### CX2: Security CrossCheck 指向 replay_class/auth tools 单源缺口
**来源**: rev-dsv4-security → 目标方向 Architect / Designer / Auth  
**发现**: `deploy_mutation`、auth tools、audience transport、CSR replay_class 等安全语义未进入机器源。  
**处置**: 升级为 B3，并列入 D2/D3 用户裁决。

## 方向专属 High 优先级

### A-H1: RoomCap “同 tick 释放”语义与 Phase 2a validator 门控不清
**来源**: rev-dsv4-architect C2，rev-dsv4-determinism Formal Issue 1  
**处置**: 在 `engine.md` / command validation 中明确 Phase 2a S06 读取的是 pre-release RoomCap；“同 tick 释放”仅适用于 Phase 2b S07→S08 的中间态，或重构 spawn validation。

### S-H1: WebSocket / audience / rate-limit 安全合同不一致
**来源**: rev-gpt-security H3，rev-dsv4-security H1/H2  
**处置**: 统一 4 段 vs 5 段 audience；明确 transport 枚举；选择握手后免签或 per-message seq+MAC；YAML 生成 rate_limit_key 和 replay class。

### D-H1: Drone lifespan + Controller repair 可能造成结构性防御偏置
**来源**: rev-dsv4-designer C2，rev-gpt-designer gameplay/onboarding concerns  
**处置**: 不阻塞 YAML 单源修复，但应进入 gameplay balance backlog。建议用模拟验证 TOUGH-heavy drone、Controller repair hard cap、防御方站位的攻防 ROI。

### P-H1: EXECUTE deadline 与 Phase 2a 串行最坏量不闭合
**来源**: rev-gpt-performance P1，rev-dsv4-performance D2  
**处置**: 给出 100k commands / 400ms 的可测预算，拆分 validation/apply microbenchmark；若无法达成，降低目标或引入 admission/batching。

### E-H1: PvE faucet / upkeep / storage tax 缺少可计算闭环
**来源**: rev-gpt-economy E2-E5，rev-dsv4-economy D2/D4/D6  
**处置**: 经济参数必须能从机器源导出 balance sheet；PvE 注入需有区域/玩家维度上限和 dashboard 校验。

### X-H1: Developer onboarding 仍会读到旧工具名、旧错误码、旧 IDL 示例
**来源**: rev-gpt-apidx C1-C3/H3，rev-dsv4-apidx C1-C5，rev-gpt-designer G1/G2  
**处置**: 删除/生成化旧参考页；给出 5 分钟 onboarding 路径，只引用 generated registry/SDK；per-tool error coverage 必须可生成。

### T-H1: f64 / SIMD / custom_action 排序边界需明确
**来源**: rev-dsv4-determinism D1/D6/D7，rev-gpt-determinism T6  
**处置**: replay-safe schema 不使用 f64；SIMD 默认与 TickTrace feature recording 二选一；custom_actions 的排序键写入 manifest 合同。

## Medium/Low 处置

| ID | 问题 | 来源方向 | 处置 |
|----|------|---------|------|
| M1 | generator provenance 缺失 | Architect/API-DX | 纳入 B1 修复；每个 generated Markdown 写 source hash + generator version |
| M2 | SwarmError / JSON-RPC envelope 多处定义不一致 | API/DX | 与 B4 一并生成化 |
| M3 | Snapshot truncation priority buckets 多版本描述 | Performance/Determinism | 修正为单一引用；不作为本轮 blocker 独立项 |
| M4 | Wasmtime 版本锁定写法不够精确 | Security/Determinism | Phase 0 文档维护项；记录完整 crate/build version 到 TickTrace/缓存键 |
| M5 | AI onboarding 缺少真正 5 分钟闭环 | Designer/API-DX | Phase 1 DX backlog；修复旧工具名后再补教程 |
| M6 | Market/Contracts/P2P/Merchant MVP 归属不稳定 | Designer/Economy | Phase 1 product scope 裁剪，不阻塞单源修复 |
| M7 | Alliance 24h 背叛冷却对短 session 玩家效果弱 | Designer | Gameplay balance backlog |
| M8 | PvE 30% faucet 阈值缺少数学推导 | Designer/Economy | 与 E-H1 共同进入经济模拟 |
| M9 | Section numbering / stale prose | Determinism | 文档清理批处理 |
| L1 | World/Arena replay 社区化表述不统一 | Designer | Low；ROADMAP/UX 文档统一措辞 |

## D-items（需用户裁决）

### D1: 单事实源覆盖范围
**问题**: 当前 YAML → `api-registry.md` 基本闭合，但其他 Markdown 仍可手写漂移。  
**选项**:
- A. 只保证 `api-registry.md` generated，其余文档允许手写引用。
- B. 所有 API/ABI/security/limit/replay/economy 机器合同相关 Markdown 都必须 generated 或 superseded。
**推荐**: B。R18 的主要失败点正是“registry 闭合但开发者文档不闭合”。

### D2: Auth 工具的机器源位置
**问题**: Auth/CSR/Recovery 工具是安全关键面，但未完整进入 `game_api.idl.yaml`。  
**选项**:
- A. 并入 `game_api.idl.yaml`，所有 MCP/API tool 一个文件。
- B. 新建 `auth_api.idl.yaml`，与 `game_api.idl.yaml` 共享 type/security/replay registry，并共同生成 registry。
**推荐**: B。auth 生命周期与 game action 变更节奏不同，但必须参与同一 drift gate。

### D3: `swarm_deploy` replay_class 表达
**问题**: prose 要求 deploy 使用 FDB version_counter 的 `deploy_mutation`，但 YAML tool 表仍容易被解释为 `idempotent_mutation`。  
**选项**:
- A. 在 replay_class enum 中显式加入 `deploy_mutation`。
- B. 保持 `idempotent_mutation`，另加 `nonce_mechanism: fdb_version_counter` 字段区分。
**推荐**: A，并可同时保留机制字段。安全语义应在 enum 层可见，避免 codegen 误映射到 Dragonfly nonce。

### D4: replay-safe API 中的 `f64`
**问题**: 多个 MCP output schema 暴露 `f64`，但确定性合同禁用 f64。  
**选项**:
- A. 改为整数/定点/basis-point 字段，并保持 replay-safe。
- B. 保留 f64，但将 replay_class 改为 display-only，不参与 replay compare。
**推荐**: A。若字段对 AI agent 决策有意义，应保持跨平台稳定。

### D5: 经济事实源形态
**问题**: Resource Ledger 的操作全集、税/维护费/退费公式未由机器源生成。  
**选项**:
- A. 扩展 `game_api.idl.yaml` 的 `resource_operation` 覆盖所有经济事件。
- B. 新建 `resource_ledger.idl.yaml`，生成 Resource Ledger、TickTrace resource schema、dashboard schema。
**推荐**: B。经济平衡迭代频率高，独立文件更易维护，但必须和 API registry 联合校验。

### D6: Worker pool 权威值
**问题**: YAML/registry 是 256，engine 推导使用 1000。  
**选项**:
- A. 以 256 为 Phase 0 默认，重算 capacity/performance 目标。
- B. 将 YAML/registry 改为 1000，并要求硬件/隔离预算证明。
**推荐**: A。先以保守值闭合合同，再用 benchmark 提升。

## D-items 裁决结果

| D# | 裁决 | 说明 |
|----|------|------|
| D1 | **B** | 全域生成化 — 所有 API/ABI/security/limit/replay 相关 Markdown 必须 generated 或 superseded |
| D2 | **B** | 新建 `auth_api.idl.yaml`，共享 drift gate |
| D3 | **A** | `deploy_mutation` 显式入 replay_class enum |
| D4 | **A** | f64→整数/定点/basis-point，replay-safe |
| D5 | **A** | 扩展 `game_api.idl.yaml` resource_operation 覆盖全部经济事件 |
| D6 | **A** | Worker pool 默认 256，重算 capacity |

## 文档维护项

1. `specs/gameplay/08-api-idl.md`：标记为 `SUPERSEDED`，或重生成，仅保留指向 `game_api.idl.yaml` / `api-registry.md` 的摘要。
2. `specs/reference/commands.md`：删除旧 RejectionReason 变体表，改为 canonical code + debug_detail 映射。
3. `specs/core/02-command-validation.md`：删除旧 schedule、旧 refund、旧 cap、旧 rejection code；引用 manifest/registry/resource ledger。
4. `specs/reference/mcp-tools.md`、`host-functions.md`、`design/interface.md`：由 YAML/registry 生成或降级为非权威指南。
5. `design/auth.md` 与 security specs：将 auth tools/replay_class/rate_limit/audience/WebSocket 安全语义机器化。
6. `design/engine.md`：删除 `MAX_POOL = 1000` 等手写权威常量，改为 registry 引用；更新容量推导。
7. `specs/core/01-tick-protocol.md` 与 `05-persistence-contract.md`：统一 TickTrace 持久化失败语义。
8. 新增或更新 CI：YAML parse → registry generation → all generated Markdown diff → stale declaration scan → fail on drift。
9. ROADMAP：加入“R18 单源闭合修复”里程碑，明确完成条件为所有 reviewer 不再能从手写 Markdown 读出不同 API/安全/确定性合同。

## R19 入场条件

- [ ] `game_api.idl.yaml` / `api-registry.md` / 所有 API reference docs 的 drift gate 通过。
- [ ] `08-api-idl.md` 不再包含旧 IDL/旧 RejectionReason/旧 CommandAction 参数。
- [ ] RejectionReason 35 canonical + debug_detail 映射在所有文档一致。
- [ ] Auth tools 与 replay_class 进入机器源；`swarm_deploy` replay class 明确。
- [ ] Host Function ABI、基础类型、error schema 可由机器源生成完整 SDK。
- [ ] worker pool、drone cap、WASM output、FDB transaction、module size 等 limits 无重复手写冲突。
- [ ] Phase 2b schedule 只保留 manifest 为权威；其他文档引用它。
- [ ] TickTrace terminal/audit/replay 语义统一；f64 replay-safe 边界关闭。
- [ ] Resource Ledger / storage tax / upkeep / recycle refund 的机器源和示例一致。

## 评审统计

| Direction | GPT-5.5 reviewer | GPT Verdict | DeepSeek V4 Pro reviewer | DSV4 Verdict | 共识强度 |
|-----------|------------------|-------------|---------------------------|--------------|----------|
| Architect | rev-gpt-architect | REQUEST_MAJOR_CHANGES | rev-dsv4-architect | REQUEST_MAJOR_CHANGES | 强：均认为 registry 主链路改善，但整体合同未闭合 |
| Security | rev-gpt-security | REQUEST_MAJOR_CHANGES | rev-dsv4-security | REQUEST_MAJOR_CHANGES | 强：auth/replay/security columns 未机器化 |
| Designer | rev-gpt-designer | CONDITIONAL_APPROVE | rev-dsv4-designer | CONDITIONAL_APPROVE | 中强：gameplay 可实施，但旧 IDL/onboarding/防御偏置需修正 |
| Performance | rev-gpt-performance | REQUEST_CHANGES | rev-dsv4-performance | CONDITIONAL_APPROVE | 中强：关键性能常量和预算未闭合 |
| Economy | rev-gpt-economy | REQUEST_MAJOR_CHANGES | rev-dsv4-economy | CONDITIONAL_APPROVE | 强：经济事实源和公式仍分裂 |
| API/DX | rev-gpt-apidx | REQUEST_MAJOR_CHANGES | rev-dsv4-apidx | REQUEST_MAJOR_CHANGES | 极强：开发者文档与 YAML/registry 大面积漂移 |
| Determinism | rev-gpt-determinism | REQUEST_MAJOR_CHANGES | rev-dsv4-determinism | REQUEST_MAJOR_CHANGES | 强：tick/replay/f64/schedule 冲突仍阻塞 |

### Verdict 分布

| Verdict | 数量 | Reviewers |
|---------|------|-----------|
| REQUEST_MAJOR_CHANGES | 9 | gpt-architect, dsv4-architect, gpt-security, dsv4-security, gpt-apidx, dsv4-apidx, gpt-determinism, dsv4-determinism, gpt-economy |
| REQUEST_CHANGES | 1 | gpt-performance |
| CONDITIONAL_APPROVE | 4 | gpt-designer, dsv4-designer, dsv4-economy, dsv4-performance |
| APPROVE | 0 | — |

### 共识强度评估

- 全轮最高共识：`game_api.idl.yaml` ↔ `api-registry.md` 直接生成链路已有显著进步，主计数基本闭合。
- 全轮核心分歧：部分评审将“YAML ↔ registry 无漂移”视为通过项，部分评审将“所有 Markdown/reference/spec/design 不漂移”视为闭合标准。Speaker 裁决采用后者，因为用户任务重点是“生成式单源是否闭合”，而实现者不会只读取 registry。
- Blocker 置信度：B1/B2/B3/B5/B6/B7 均为跨方向、跨模型重复发现，属于必须修复项。
- 结论：R18 不是架构方向错误，而是单源边界定义不足和手写文档残留过多。修复策略应以“生成化 / supersede / CI drift gate”为主，而不是继续手工逐表改数字。
