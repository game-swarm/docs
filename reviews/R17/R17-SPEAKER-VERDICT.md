# Swarm 设计评审 R17 — Speaker 共识报告

## 裁决概要

- 本轮目标：在 R15-R16 两轮修复后，验证“权威单一事实源闭合”是否真正成立，并判断是否可进入实现。
- Phase 1 完成情况：14/14 reviewers 全部完成并已读取。
- Phase 2 补漏情况：本任务未要求启动补充评审；本报告基于 14 份 Phase 1 全量报告综合。各评审员 CrossCheck 已被纳入本报告的共识聚类，但未创建额外 Phase 2 看板任务。
- 收敛评估：R17 相比 R15/R16 有明显进展，尤其是 IDL-first、Phase 2b manifest、持久化分层、WASM-only、visibility/security 设计方向都获得多方认可；但“单事实源闭合”仍未达成。当前问题不是机制缺失，而是多个文档都在声明权威，且同一合同在 IDL、registry、设计说明、reference/spec 中出现不同版本。
- Freeze 状态：不建议 Freeze。必须先完成一次“IDL/registry/reference 文档收口 + CI drift gate”后再复评。

## 总体 Verdict

REQUEST_MAJOR_CHANGES

理由：14 份报告中 9 份为 REQUEST_MAJOR_CHANGES，5 份为 CONDITIONAL_APPROVE，无 APPROVE。REQUEST_MAJOR_CHANGES 横跨 Architect、Security、API/DX、Performance、Economy、Determinism 多方向，且核心问题集中于同一类：权威源未机械闭合。Designer 方向总体较乐观，但也确认 onboarding 工具、错误码、经济/MVP 边界、profile 分配等会影响游戏体验。

## 共识 Blocker（跨方向 + 跨模型同意）

### B1: IDL 与 API Registry 未形成真实生成闭环

**方向 × 模型矩阵**:
- Architect: rev-gpt-architect A1, rev-dsv4-architect C1
- Security: rev-gpt-security H5, rev-dsv4-security C1
- API/DX: rev-gpt-apidx X1, rev-dsv4-apidx C1
- Performance: rev-gpt-performance P1, rev-dsv4-performance M1
- Determinism: rev-gpt-determinism T1

**问题**:
`game_api.idl.yaml` 与 `api-registry.md` 在最基础字段上已不一致：IDL 为 `api_version: 0.2.0`，Registry Markdown 仍写 `0.1.0`。API/DX 还指出 MCP tools 声明总数 46，但具体列表疑似为 45。多个评审员指出 Markdown 虽声称由 YAML 生成、冲突以 YAML 为准，但事实证明生成链或 CI drift gate 没有运行。

**修正要求**:
1. 明确 `game_api.idl.yaml` 为 API/limits/error/host ABI/TickTrace schema 的唯一机器权威源。
2. 重新生成 `api-registry.md`，修复 `api_version`、tool count、MCP tool list、replay_class、visibility field、rate limit、subject_source 等字段。
3. 添加 CI gate：Markdown 中出现的版本、总数、enum、field、tool name、rate limit、replay_class 必须与 YAML 一致；禁止手改 generated tables。
4. 在文档中标明哪些 Markdown 文件是 generated，哪些是 explanatory，不允许 explanatory 文档重复定义可冲突表格。

### B2: RejectionReason / CommandAction / validation 闭包仍断裂

**方向 × 模型矩阵**:
- API/DX: rev-gpt-apidx X3/X4, rev-dsv4-apidx C2/L2/L5
- Determinism: rev-gpt-determinism T2/T3
- Architect: rev-gpt-architect A2/A4
- Security: rev-gpt-security M2
- Designer: rev-gpt-designer G2, rev-dsv4-designer CrossCheck 1

**问题**:
Registry/IDL 声称 `RejectionReason` 为 35 个变体，但 `02-command-validation.md`、`commands.md`、`08-api-idl.md`、`09-snapshot-contract.md` 中仍使用大量未注册或命名不一致的错误码，例如 `NotMovable`、`Fatigued`、`MissingBodyPart`、`TileBlocked`、`SourceEmpty`、`TargetFull`、`NotYourRoom`、`AlreadyHacked`、`InvalidDamageType`、`MainActionQuotaExceeded` 等。CommandAction 也有 `Claim`/`ClaimController`、`UpgradeController`、`15 + Custom + 8 special attacks` vs `19 core variants` 等漂移。

**修正要求**:
1. 从所有 reference/spec/design 文档中机器抽取 `RejectionReason` 与 `CommandAction` token，与 IDL 做反向比对。
2. 选择统一策略：
   - 要么把 validation 中所有可达错误码正式注册进 IDL；
   - 要么把 validation 文档改写为只使用 IDL 中的 canonical code，并把细粒度教学原因移入 non-wire `diagnosis/detail`。
3. 建立 `CommandAction → validator → apply handler/system_id → rejection set → resource/fuel ledger effect` 的生成闭包矩阵。
4. 系统 manifest 的 handled command 必须只引用 IDL action name；internal event 必须显式标注，不得伪装为 CommandAction。

### B3: MCP tool surface 与 onboarding/self-discovery 合同不闭合

**方向 × 模型矩阵**:
- API/DX: rev-gpt-apidx X2/X8/X9, rev-dsv4-apidx C3/C4/M2
- Designer: rev-gpt-designer G1, rev-dsv4-designer CrossCheck 3/G6
- Security: rev-gpt-security M1/M5/CrossCheck 8, rev-dsv4-security M2

**问题**:
IDL/Registry、`design/interface.md`、`mcp-tools.md`、feedback-loop/onboarding 文档之间存在三套 MCP 工具名与 profile 分配。onboarding 依赖 `swarm_get_schema`、`swarm_get_docs`、`swarm_get_available_actions`、`swarm_explain_last_tick`、CSR/auth tools 等，但这些工具不在当前 IDL 工具表中或名称不同。auth bootstrap tools 在 auth/interface 文档中存在，却未纳入 IDL 或独立 registry。

**修正要求**:
1. 以 IDL tool list 为唯一 MCP tool nameset；所有 interface/mcp-tools/onboarding 表格必须生成或引用。
2. 明确 auth/onboarding tools 是加入 `game_api.idl.yaml`，还是放入独立 Auth API registry；不能停留在设计文档中却被“未注册 CI 拒绝”。
3. 定义 5-call 以内的 Onboarding Happy Path，并确保每个工具在 IDL 中具备 input/output/error schema、scope、rate limit、replay_class。
4. 统一 profile/category：经济运营工具若为日常 play 信息，不应在 interface 中归为 debug，而 registry 又归为 Play/Economy。

### B4: 安全关键字段在权威源之间冲突

**方向 × 模型矩阵**:
- Security: rev-gpt-security H1-H5, rev-dsv4-security C2/H1-H3
- API/DX: rev-gpt-apidx X2/X6/X7, rev-dsv4-apidx H4
- Architect: rev-dsv4-architect H3

**问题**:
安全合同仍有多处互斥定义：
- Agent WebSocket 握手后是否免签：`auth.md` 写会话内免签，MCP/Registry/IDL 要求每消息 seq + MAC/signature。
- deploy replay class：auth/command-source 要 `deploy_mutation + FDB version_counter`，IDL/registry 仍标为 `idempotent_mutation`。
- 多个 MCP tool 接收客户端 `player_id`，与“subject 从证书提取，不允许客户端自报”的安全模型冲突。
- visibility oracle 修复在安全文档中要求 `omitted_count` 分桶，但 IDL/registry 仍为精确 `u32`。
- admin/read nonce、rate limit、audience transport、auth bootstrap registry 仍有不一致。

**修正要求**:
1. Agent WS：握手只绑定 identity；所有敏感/写消息必须 per-message seq + MAC/signature；仅 browser spectator read-only WS 可免签。
2. deploy：IDL 改为 `deploy_mutation`，结构化记录 `replay_guard=fdb_version_counter`、`version_scope=player_id+module_slot`、`client_nonce=forbidden`。
3. 当前主体查询与 deploy input schema 删除或禁止客户端 supplied `player_id`；admin 查询使用 `target_player_id + required_scope=admin`。
4. visibility truncation 字段从精确计数改为分桶 enum，并添加 invariant CI。
5. auth bootstrap 工具纳入机器注册表或独立 Auth registry。

### B5: TickTrace / persistence / failure semantics schema 不闭合

**方向 × 模型矩阵**:
- Architect: rev-gpt-architect A3/A7
- Performance: rev-dsv4-performance H3/H2, rev-gpt-performance P1
- Determinism: rev-gpt-determinism T1/T8

**问题**:
R16 B3 引入的 `collect_id`、`attempt_id`、`commit_id`、`terminal_state` 在 `engine.md` 与 `persistence-contract.md` 中被视为 retry/commit 追踪关键字段，但 `api-registry.md` 与 IDL 的 TickTrace Envelope 仍为 22 字段且未包含这些字段。与此同时，tick protocol 的 failure matrix 仍残留“TickTrace write fail 但 tick 成功、审计不完整”的旧语义，与 persistence contract 中“canonical blob/object write fail → tick 放弃”的语义冲突。Performance 还指出对象存储 prewrite + 5s timeout 与 COMMIT ≤50ms/20ms 预算冲突。

**修正要求**:
1. 决定 `collect_id/attempt_id/commit_id/terminal_state` 是否属于公共权威 TickTrace schema；若是，加入 IDL 并更新 total_fields；若不是，从 engine/API 公共 envelope 中移除并限定为 persistence internal。
2. 删除 tick protocol failure matrix 中“状态成功但 canonical TickTrace/replay 缺失”的旧路径。
3. 区分 canonical TickTrace blob 与 analytics/replay artifacts；前者必须有强一致故障语义，后者可 best-effort。
4. 重新设计 object-store 写入是否在 tick critical path：若保留 prewrite，预算必须真实包含对象存储 p99；若不保留，需 WAL/hash proof + pending_upload 状态。

### B6: Determinism 关键路径存在多处跨文档冲突

**方向 × 模型矩阵**:
- Determinism: rev-gpt-determinism T4/T5/T6/T7, rev-dsv4-determinism D1/D2/D3
- Architect: rev-dsv4-architect C2/C3, rev-gpt-architect A6
- Performance: rev-gpt-performance P1/P2

**问题**:
确定性闭包仍有可导致 replay/实现分叉的问题：
- `02-command-validation.md` 与 `06-phase2b-system-manifest.md` 对 special/status/regeneration/decay 调度顺序冲突。
- WASM output >256KB 在不同文档中被描述为 prefix truncation、整批丢弃、schema fail、1MB batch cap 等多种语义。
- snapshot truncation 在 `engine.md` 与 tick protocol 中有不同 bucket/priority 算法。
- IDL/MCP 输出包含大量 `f64`，与“确定性数值禁 f64”的合同冲突；至少需标明 presentation-only 或改为定点。
- StatusState parallel set 是否并行安全不明确：如果是同一 Component enum variant，S16-S22 并行写同一 Component 不安全。

**修正要求**:
1. `06-phase2b-system-manifest.md` 成为唯一调度权威；validation/tick protocol 只引用，不重写第二套调度图。
2. WASM output 超限统一为一种语义；从安全/确定性/性能共识看，建议 `>256KB 整批丢弃，不解析前缀`。
3. snapshot truncation 形成 versioned authoritative algorithm，并通过 IDL/manifest 引用。
4. 所有进入 deterministic state/checksum/simulate trace 的数值必须整数/定点；MCP presentation f64 必须明确 non-authoritative。
5. StatusState subtype 若是独立 Component，拆 R/W matrix；若是单一 Component variant，S16-S22 串行或 partition by entity。

## CrossCheck 补漏发现（基于 Phase 1 CrossCheck 聚合）

本轮没有独立 Phase 2 补充任务；以下为 Phase 1 CrossCheck 聚合后的补漏发现。

### CX1: Auth/bootstrap 工具未注册到机器源

**来源**: rev-gpt-security, rev-dsv4-security, rev-gpt-apidx, rev-dsv4-apidx → 目标方向: API/DX / Security
**发现**: `swarm_get_server_trust`、`swarm_register_challenge`、`swarm_submit_csr` 等 auth/onboarding tools 存在于 auth/interface/mcp-tools 文档，但不在 IDL 46 tools 中。
**处置**: 升级为 Blocker B3/B4。需加入 IDL 或建立独立 Auth API registry。

### CX2: Economic tools profile 归属冲突

**来源**: rev-dsv4-designer → 目标方向: API/DX / Designer
**发现**: `swarm_get_economy`、`swarm_get_drone_efficiency`、`swarm_get_economy_trend` 在 api-registry 中属于 Play/Economy，但 interface capability profile 将其归为 debug。
**处置**: Medium/High。若人类 Web UI 能看到等价运营指标，则 AI agent 的 MCP profile 也应能访问，建议以 registry 为准。

### CX3: Sandbox OS 加固表内部不一致

**来源**: rev-gpt-security, rev-dsv4-security → 目标方向: Security / Performance
**发现**: clone/clone3/fork/vfork、pids.max 16 vs 32、net namespace “无网络”表述存在矛盾。
**处置**: Medium。作为安全部署表必须单源化，建议统一到一张 OS hardening checklist 并由 CI/部署脚本验证。

### CX4: Phase 2b manifest 对部分方向不可见导致闭包证明缺口

**来源**: rev-gpt-performance → 目标方向: Architect / Performance
**发现**: Performance 子集未包含 `06-phase2b-system-manifest.md`，但性能预算依赖其 R/W matrix 与并行性证明。
**处置**: Medium。后续两级阅读映射应把 manifest 加入 Performance 必读，或在 tick protocol 中提供 generated R/W summary。

## 方向专属 High 优先级

### A-H1: Status Effects Parallel Set B 并行安全不明

来源：rev-dsv4-architect C3。
若 `StatusState` 是单一 Component enum，则 S16-S22 并行写同一 component column，Bevy 并行调度不安全。需拆 subtype component 或串行化/partition by entity。

### A-H2: RoomCap 与 Spawn 同 tick 槽位释放语义需文档化

来源：rev-dsv4-architect H2。
S06 spawn_validator 在 Phase 2a 读取 RoomCap，看不到 S07 death_marker 在 Phase 2b 释放的槽位。可接受“保守延迟一 tick”，但必须明示，避免实现者以为同 tick 释放可被 S06 使用。

### S-H1: WebSocket per-message auth 与 deploy replay class

来源：rev-gpt-security H1/H2，rev-dsv4-security C2/L2。
这是安全方向最高优先级：会话内免签与 `idempotent_mutation` deploy 都会直接导致重放/会话注入/实现降级风险。

### D-H1: Soft_launch → PvP 悬崖与 first-hour 链路

来源：rev-dsv4-designer G1，rev-gpt-designer G1/G4。
Designer 方向认为首小时体验成型，但新玩家从 safe/soft launch 到完整 PvP 的过渡仍可能形成留存风险；同时 onboarding 工具名不一致会破坏 AI 自举。建议在文档中加入渐进退出或首次攻击保险，并清除 first-hour 中依赖 RFC market/contract 的路径。

### D-H2: World 长期目标与战术空间深度

来源：rev-dsv4-designer G2-G4，rev-gpt-designer G6/Fresh Ideas。
不阻塞权威源修复，但应进入 Phase 1+ backlog：World 需要更强内生目标/世界事件，Arena 纯战术层需要更高空间深度或明确 Phase 2 扩展点。

### P-H1: Object store prewrite 与 aggregate CPU admission

来源：rev-gpt-performance P1/P1，rev-dsv4-performance H1/H2。
性能方向最大风险不是单玩家预算，而是全局聚合：对象存储写入进入 commit critical path、500/1000 players aggregate sandbox CPU 超过 32-core 预算、worker pool 公式分叉。需给出真实容量模型与 admission policy。

### P-H2: FDB transaction size 与 worker pool 公式分叉

来源：rev-dsv4-performance H1/H2。
`<10KB` vs `<10MB` 差三数量级；worker pool `max(min_pool, active_players)` vs `min(max_pool, active_players)` 语义相反。必须统一到权威参数表。

### E-H1: 经济参数权威源冲突

来源：rev-gpt-economy E1-E4，rev-dsv4-economy D1-D3。
Recycle refund、storage tax、global transfer delay、upkeep 示例/公式、allied transfer、market RFC 边界均需收口。经济方向不是设计理念问题，而是参数权威源冲突。

### X-H1: Host Function ABI 与 JSON-RPC error envelope 不一致

来源：rev-gpt-apidx X5/X6，rev-dsv4-apidx H1/H4。
`host_get_terrain`、`host_get_world_rules`、`host_path_find` 在 IDL/registry 与 interface/host-functions 之间签名不同；error envelope numeric JSON-RPC code vs string `RejectionReason` 混用。SDK/codegen 前必须统一。

### T-H1: f64/time fields 与 deterministic contract 边界

来源：rev-dsv4-determinism D1，rev-gpt-determinism T7。
MCP/API 输出中的 f64 与 timestamp/deployed_at/expiry 等必须明确不进入 canonical state/hash；若会进入 replay/simulate/AI-codegen 决策，应改为定点或 tick/versionstamp 表示。

## Medium/Low 处置

| ID | 问题 | 来源方向 | 处置 |
|----|------|----------|------|
| M1 | Snapshot/simulate/dry-run schema 缺少 `not_predictive`、`deterministic`、`omitted_categories` 等安全标志 | API/DX, Designer | 并入 B3/B6；IDL 输出 schema 补齐 |
| M2 | Capability profile/category taxonomy 混乱，`Economy` category 与工具条目不一致 | API/DX, Designer | 以 IDL 显式 tool-name arrays 或 generated category expansion 为准 |
| M3 | SDK onboarding path 不足 5-minute happy path | API/DX, Designer | 新增 generated onboarding section + smoke test |
| M4 | Rate limit 格式与 source-level/per-tool 限流关系不清 | Security, API/DX | 在 registry 中定义叠加规则；security docs 只引用 |
| M5 | Pathfinding fair-share 在 500/1000 players 下过低 | Performance | 进入容量模型修订；可考虑 active_path_users / demand-based share |
| M6 | Bevy rollback snapshot 深拷贝缺大小模型 | Performance | 增加 WorldState bytes cap 与 COW/delta journal 方案 |
| M7 | Drone communication 缺失影响 swarm fantasy | Designer | Phase 2 RFC，不阻塞当前权威源修复 |
| M8 | Replay visibility presets / Safe Share 产品合同不足 | Designer | Phase 1+ 文档补充，不阻塞 API closure |
| M9 | SIMD World 默认 true 与 fuel/fairness/calibration 未闭合 | Determinism, Performance | 明确回放不重跑 WASM；审计重跑需匹配 arch/SIMD；补 fuel benchmark |
| L1 | Wasmtime/Cargo lock version pinning需更精确 | Security | Low，CVE-SLA 中统一 |
| L2 | historical R15/R16 notes 残留在 reference docs | API/DX | 移至 changelog/reviews，reference 只保留当前状态 |
| L3 | Tutorial dry-run snapshot 不代表 World 条件 | Designer | Smoke test 增加 representative fog/PvP snapshot |

## D-items（需用户裁决）

### D1: RejectionReason 策略 — 扩展 wire enum 还是分层诊断

**问题**: validation 文档使用的细粒度错误码远多于 IDL 35 个 canonical code。安全方向又希望避免过细错误造成 oracle。
**选项**:
- A: 把所有 validation 可达错误码注册为 wire-level RejectionReason，并用 mode/profile 控制暴露粒度。
- B: wire-level 保持较少 canonical code；细粒度原因进入 admin/internal/pedagogical diagnosis，不进入稳定协议 enum。
**推荐**: B。理由：兼顾安全 opaque error、SDK 稳定性与教学解释；但需明确 diagnosis schema 与生成来源。

### D2: JSON-RPC error envelope wire shape

**问题**: interface 示例使用 numeric `error.code=-32000 + data.swarm_error`，Registry/IDL 使用 string `error.code=RejectionReason`。
**选项**:
- A: 标准 JSON-RPC numeric code 保持协议层，`error.data.swarm_error.code` 存 canonical string。
- B: 直接把 `error.code` 改为 string RejectionReason。
**推荐**: A。理由：更符合 JSON-RPC/MCP 生态，客户端 parser 更稳定；Swarm-specific code 放在 data。

### D3: Recycle refund 公式权威值

**问题**: IDL/gameplay 有固定 50%，resource-ledger 有按剩余寿命 10%-50% 比例，二者经济含义不同。
**选项**:
- A: 固定 50%。简单但鼓励到期前回收，削弱 lifespan。
- B: `max(body_cost*10%, body_cost*0.5*remaining/total)` 或等价比例公式。
**推荐**: B。理由：两位 Economy reviewer 都认为比例公式更能避免套利并保留时机 trade-off。

### D4: Storage tax 模型

**问题**: resource-ledger flat 10bp/tick vs gameplay/balance-sheet tiered 0/1/5/20bp。
**选项**:
- A: flat 10bp/tick。
- B: tiered occupancy-based tax。
**推荐**: B。理由：tiered tax 更符合 anti-hoarding 均衡证明，也更少惩罚适度存储。

### D5: Object-store write 是否在 tick critical path

**问题**: canonical TickTrace blob prewrite 保证 commit 后可读，但对象存储 p99/5s timeout 与 tick COMMIT 预算冲突。
**选项**:
- A: 保持 prewrite；重写 tick budget，把对象存储 p99 纳入硬预算。
- B: FDB commit 只依赖 WAL/hash/pending_upload，object store 异步上传。
**推荐**: B。理由：Performance 共识认为 prewrite 会把外部存储尾延迟引入 tick critical path；B 保留 hash proof 可审计性同时提升可用性。

### D6: Soft_launch 退出方式

**问题**: 新玩家从 PvE-only soft launch 到完整 PvP 是二元切换，Designer DSV4 认为存在留存风险。
**选项**:
- A: 保持 1500 tick soft_launch + 50 tick warning。
- B: 增加渐进 PvP 伤害/损失比例或首次被攻击保险。
**推荐**: B。理由：不改变核心规则，但显著降低首次 PvP 被碾压的 churn 风险。

## 文档维护项

1. 增加 `docs/authority-map.md` 或在 README 中明确权威层级：
   - `game_api.idl.yaml`: API/tool/action/error/host ABI/limits/TickTrace schema 权威。
   - `06-phase2b-system-manifest.md`: ECS system schedule/RW matrix 权威。
   - `05-persistence-contract.md`: storage/failure semantics 权威。
   - `08-resource-ledger.md`: economic operation/order/formula 权威。
   - design docs: rationale 与产品解释，不重复可冲突数值表。
2. 将 generated Markdown 表格标记为 generated-from-IDL，并提供生成命令与 CI drift check。
3. 全库扫描并清理 stale tool names、stale RejectionReason、old command examples、old JSON-RPC envelope examples。
4. reference docs 移除 R15/R16 历史修复说明，历史内容迁移到 reviews/changelog。
5. 更新 review two-level reading 映射：Performance 必读 `06-phase2b-system-manifest.md`，API/DX 必读 `mcp-tools.md/host-functions.md/commands.md`，Economy 必读 `resource-ledger.md` 与 balance sheet。
6. R18 前建议先做一次“contract cleanup pass”，而不是直接进入新一轮全量设计评审。

## R18 入场条件

R18 review 前至少满足：
1. `game_api.idl.yaml` 与 `api-registry.md` 完全一致，版本/总数/工具/enum/fields 可由 CI 验证。
2. `RejectionReason` 与 `CommandAction` 在 validation/reference/snapshot docs 中无未注册 token。
3. MCP onboarding/auth tools 进入 IDL 或独立 registry，interface/mcp-tools 与 registry 无 nameset drift。
4. WebSocket per-message auth、deploy replay class、subject_source/player_id、visibility omitted count 在 IDL/security docs 中一致。
5. TickTrace Envelope 与 persistence retry fields 决策完成，并同步 IDL/registry/engine/persistence。
6. WASM output >256KB、snapshot truncation、Phase 2b schedule、StatusState parallelism 形成单一权威合同。
7. Economy core parameters（recycle refund、storage tax、global transfer delay、upkeep examples、market/allied boundary）归入 Resource Ledger 并统一。

## 评审统计

### Verdict 矩阵

| Direction | GPT-5.5 | DeepSeek V4 Pro |
|-----------|---------|-----------------|
| Architect | REQUEST_MAJOR_CHANGES | REQUEST_MAJOR_CHANGES |
| Security | REQUEST_MAJOR_CHANGES | REQUEST_MAJOR_CHANGES |
| Designer | CONDITIONAL_APPROVE | CONDITIONAL_APPROVE |
| Performance | REQUEST_MAJOR_CHANGES | CONDITIONAL_APPROVE |
| Economy | REQUEST_MAJOR_CHANGES | CONDITIONAL_APPROVE |
| API/DX | REQUEST_MAJOR_CHANGES | REQUEST_MAJOR_CHANGES |
| Determinism | REQUEST_MAJOR_CHANGES | CONDITIONAL_APPROVE |

### Severity/Signal 汇总

- REQUEST_MAJOR_CHANGES: 9/14
- CONDITIONAL_APPROVE: 5/14
- APPROVE: 0/14
- REJECT: 0/14
- 最高共识问题类型：权威源 drift、IDL/Registry 未生成闭环、RejectionReason/CommandAction 未闭合、MCP tool surface drift、安全关键字段冲突、TickTrace/persistence schema drift、determinism schedule/output/schema 冲突。
- 共识强度：高。虽然各方向的关注点不同，但多方向、多模型反复指向同一根因：文档层面已经足够详细，但缺少机械单源生成与反向 CI 校验，导致“多个权威源”同时存在。

## D-items 裁决结果

| D# | 裁决 | 说明 |
|----|------|------|
| D1 | **A** | `game_api.idl.yaml` 为唯一机器事实源，`api-registry.md` 全量生成 |
| D2 | **B** | 少量 canonical RejectionReason，detail 不进 wire |
| D3 | **B** | Recycle lifespan 比例 10-50% |
| D4 | **B** | Storage tax tiered 0/1/5/20bp |
| D5 | **B** | Object-store blob 异步上传，FDB commit 只依赖 manifest+hash |
| D6 | **B** | soft_launch→PvP 渐进退出 + 首次被攻击保险 |

## Speaker 最终结论

R17 不是“设计方向失败”，而是“权威源工程未闭合”。当前设计已经具备高质量的架构与玩法骨架；阻塞进入实现的原因是实现者无法可靠判断哪份文档是最终合同。下一步应集中做 contract cleanup：把 IDL/Registry/Reference/Spec 的重复表格收束为可生成、可校验、可追溯的单一事实源。完成后再进行 R18。