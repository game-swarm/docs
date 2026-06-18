# Swarm 设计评审 R19 — Speaker 闭合验证共识报告

## 裁决概要

- 本轮类型：Closure Verification。目标不是重新评审设计，而是验证 R18 跟踪项是否在 R19 文档集中闭合。
- Phase 1 / Reviewer 完成情况：14/14 reviewers 完成并写入 `/data/swarm/docs/reviews/R19/rev-*-*.md`。
- Phase 2 补漏情况：不适用。本轮为编号项闭合验证，不执行两级阅读补漏流程。
- 收敛评估：R19 相比 R18 有实质进展：`game_api.idl.yaml` 与 `api-registry.md` 主链路建立，35 canonical RejectionReason、46 active MCP tools、安全列、TickTrace envelope、deploy/persistence 主干均已有机器源。但闭合仍停留在“主链路改好、派生/旁路文档未清干净”的状态；多个 R18 Blocker / D-item 在不同文档层仍残留。
- Freeze 状态：**NOT FROZEN**。存在跨方向、跨模型同意的残留 GAP，不能宣布冻结。

## 总体 Verdict

**REQUEST_MAJOR_CHANGES**

理由：14 份报告中 8 份为 `REQUEST_MAJOR_CHANGES`，5 份为 `CONDITIONAL_APPROVE`，1 份为 `APPROVE`。更重要的是，至少 6 类问题被多个方向和多个模型反复确认：

1. RejectionReason canonical 设计未传播到命令校验/旧接口文档。
2. MCP/Auth 工具命名空间仍与 IDL/API Registry 分叉。
3. `swarm_deploy` 的 `replay_class` 与 deploy_mutation 防重放语义冲突。
4. IDL 仍保留多处 `f64`。
5. worker pool `256` vs `MAX_POOL=1000` 容量推导冲突。
6. Recycle / StorageTax / ResourceOperation 的经济机器源边界未闭合。

## FROZEN / NOT FROZEN

**NOT FROZEN**

冻结失败原因不是缺少总体方向，而是缺少“可实现的单一事实源闭包”：

- 主权威链路 `game_api.idl.yaml → api-registry.md` 基本成形。
- 但 `design/interface.md`、`mcp-tools.md`、`commands.md`、`02-command-validation.md`、`08-api-idl.md`、`design/engine.md`、`05-persistence-contract.md`、`09-snapshot-contract.md`、`design/auth.md` 等仍保留旧枚举、旧工具名、旧状态机、旧容量数字或旧经济公式。
- 因此实现者仍可能按不同文档得到不同 SDK、不同 replay verifier、不同 capacity model、不同经济结算规则。

## 共识 Blocker（跨方向 + 跨模型同意）

### B19-1: B1/B2 残留 — RejectionReason canonical 未全链路传播

**方向 × 模型矩阵**:
- API/DX: rev-dsv4-apidx, rev-gpt-apidx
- Designer: rev-dsv4-designer, rev-gpt-designer
- Performance: rev-gpt-performance
- Economy: rev-gpt-economy（经济域的 YAML/Markdown 断裂）
- Security: rev-gpt-security（Auth/Deploy 链路中的生成源断裂）

**问题**:
`game_api.idl.yaml` / `api-registry.md` 已有 35 canonical RejectionReason + `debug_detail` + `detail_level`，但多个派生或旁路文档仍把旧的细分原因当作 wire enum 使用，例如 `Fatigued`、`MissingBodyPart`、`NotMovable`、`TileBlocked`、`SourceEmpty`、`TargetFull`、`AlreadyHacked` 等。`design/interface.md` 还保留旧 `InsufficientResources` 复数与旧 error envelope 示例。结果是 B2 的“主源闭合”成立，但 B1 的“全链路不双写”未闭合。

**修正要求**:
1. 清理 `02-command-validation.md`、`commands.md`、`design/interface.md`、`08-api-idl.md` 中所有非 canonical RejectionReason wire code。
2. 旧细分原因只能进入 `debug_detail` 示例，不得作为 enum/table 主值。
3. 增加 CI：扫描所有 docs/specs，禁止出现未注册的 RejectionReason 作为 wire code。
4. 非权威 Markdown 若必须展示错误码表，必须由同一 YAML 生成；否则只保留指向 `api-registry.md §2` 的链接。

### B19-2: B3/B5 残留 — MCP/Auth 工具命名空间仍未收敛

**方向 × 模型矩阵**:
- API/DX: rev-dsv4-apidx, rev-gpt-apidx
- Designer: rev-dsv4-designer, rev-gpt-designer
- Security: rev-gpt-security
- Performance: rev-gpt-performance（工具/机制命名分叉相关）

**问题**:
`api-registry.md` / YAML 中 active MCP tools 为 46 个，但 `design/interface.md` 与 `mcp-tools.md` 仍列出大量 phantom / legacy tools，例如 `swarm_get_docs`、`swarm_get_schema`、`swarm_get_available_actions`、`swarm_explain_last_tick`、`swarm_inspect_entity`、`swarm_rollback`、`swarm_list_modules` 以及大量旧 Auth 工具。安全方向还发现：`design/auth.md` 中认证生命周期工具与 `game_api.idl.yaml` 中仅有的 `swarm_auth_login` / `swarm_auth_refresh` 不一致，且任务指定的 `auth_api.idl.yaml` 不存在。

**修正要求**:
1. 二选一明确 Auth API 机器源：
   - A. 新增并维护 `specs/reference/auth_api.idl.yaml`；或
   - B. 明确 Auth API 已合并到 `game_api.idl.yaml`，并把 Auth 全量工具、scope、rate limit、visibility、replay_class 纳入其中。
2. `design/interface.md` / `mcp-tools.md` 删除完整工具清单，或从 YAML 自动生成；不得继续手写不同工具表。
3. 对所有 active tools 增加“registry-only”校验：文档中出现的 `swarm_*` / `resources/*` 工具名必须存在于 IDL active 或 RFC 区，并标注状态。
4. 若旧 Auth 工具被废弃，必须给迁移表；若未废弃，必须进入机器源。

### B19-3: DA1 残留 — `swarm_deploy.replay_class` 与 deploy_mutation 防重放语义冲突

**方向 × 模型矩阵**:
- Security: rev-dsv4-security, rev-gpt-security
- Performance: rev-gpt-performance
- API/DX: rev-dsv4-apidx / rev-gpt-apidx 均确认 deploy_mutation 机制存在，但未消除字段语义争议

**问题**:
`design/auth.md` 将 `deploy_mutation` 与 `idempotent_mutation` 明确区分：前者依赖 FDB `version_counter` 防重放，后者依赖 Dragonfly nonce/time-window。可是 `game_api.idl.yaml` / `api-registry.md` 中 `swarm_deploy.replay_class` 仍是 `idempotent_mutation`，同时 notes / deploy section 又说使用 deploy_mutation pattern。这会让实现者在安全策略上选择错误的防重放机制。

**修正要求**:
1. 在 IDL replay_class 枚举中新增 `deploy_mutation`，或明确重命名字段使其区分“机制”与“replay class”。
2. 若 R18/DA1 的裁决是 `deploy_mutation replay_class`，则 `swarm_deploy.replay_class` 必须改为 `deploy_mutation`。
3. 重新生成 `api-registry.md`，并增加 CI：工具表字段不得与章节说明/notes 冲突。

### B19-4: DA2 残留 — IDL 权威源仍含 `f64`

**方向 × 模型矩阵**:
- API/DX: rev-dsv4-apidx, rev-gpt-apidx
- Architect: rev-dsv4-architect, rev-gpt-architect
- Determinism: rev-dsv4-determinism, rev-gpt-determinism
- Economy: rev-gpt-economy
- Performance: rev-gpt-performance
- Security: rev-gpt-security（N/A 但列为需复核）

**问题**:
`game_api.idl.yaml` 仍有多处 `f64`：`income_rate`、`distance`、`cost`、`progress`、`income`、`expenses`、`storage_tax`、`maintenance`、`efficiency`、`confidence`、`base_value` 等。部分 reviewer 将其解释为 display-only，不影响内部 replay；但 IDL 是 codegen/SDK/CI 的机器源，若 wire schema 仍生成浮点类型，就未闭合“f64→fixed-point”的裁决。

**修正要求**:
1. 在 IDL 中定义 fixed-point 类型族，例如 `BasisPoints`, `MilliUnits`, `ResourceRateI64`, `ProgressBps`, `ConfidenceBps`, `{ value_i64, scale }` 等。
2. 将所有 `f64` 字段迁移为 fixed/int/string decimal 中的一种，并写明单位、scale、舍入规则、序列化规则。
3. 如确有 display-only 字段，必须显式标注 `non_authoritative_display_only: true`，并禁止进入 replay checksum / TickTrace / canonical codec；但推荐仍不用 `f64`。
4. 增加 CI：`game_api.idl.yaml` 中默认禁止 `f64`。

### B19-5: B7/DA3 残留 — worker pool `256` 与 engine `MAX_POOL=1000` 冲突

**方向 × 模型矩阵**:
- Architect: rev-gpt-architect（rev-dsv4-architect 也建议重算）
- Determinism: rev-dsv4-determinism, rev-gpt-determinism
- Performance: rev-dsv4-performance, rev-gpt-performance
- API/DX: rev-gpt-apidx 提到容量派生冲突

**问题**:
IDL/API Registry 权威值是 `worker_pool_max = 256` / `max_pool = 256`，但 `design/engine.md` 仍以 `MAX_POOL = 1000` 推导 450/750/1000 player 场景。部分报告认为 `1000` 可解释为编译期 hard cap、`256` 为运行时 default；但文档未明确这种关系，且现有容量论证直接使用 1000 workers，导致 B7 容量证明不能从权威 256-worker 合同推出。

**修正要求**:
1. 明确单一语义：`worker_pool_default = 256`、`worker_pool_max_hard_cap = ?` 是否二者并存。
2. 若 DA3 裁决要求默认 256，则 `engine.md` 的性能推导必须按 256 worker 重算 500/1000 active players 场景。
3. 若保留 hard cap 1000，必须在 IDL limits 中显式建模为不同字段，并写出 `default ≤ hard_cap` 与配置约束。
4. 增加一致性检查：所有 capacity examples 不得引用过期 pool 值。

### B19-6: B6/D3/D4 残留 — 经济规则在 Resource Ledger 与机器源之间未闭合

**方向 × 模型矩阵**:
- Economy: rev-gpt-economy（rev-dsv4-economy 判定 Markdown Resource Ledger 已闭合）
- Determinism: rev-gpt-determinism, rev-dsv4-determinism（D4 snapshot stale）
- Performance: rev-gpt-performance
- API/DX: rev-gpt-apidx
- Designer: rev-dsv4-designer, rev-gpt-designer（D3 Recycle 残留）

**问题**:
经济方向出现明确分歧：rev-dsv4-economy 认为 `08-resource-ledger.md` 已作为唯一经济权威，D3/D4 CLOSED；rev-gpt-economy 和多个技术方向认为 R19 约束下 IDL/YAML 是机器权威源，而 Resource Ledger 的 `StorageTax`、`RecycleRefund`、`UpkeepDeduction`、`PvEAward`、`BuildCost`、`SpawnCost`、`AlliedTransfer` 及费率参数未进入机器可读源。同时多个文档仍有旧口径：Recycle 固定 50%、StorageTax 平税率 0.1%/tick、小数费率 0.01/0.05。

**修正要求**:
1. 用户/设计方需明确经济机器源边界：
   - A. `08-resource-ledger.md` 是唯一权威 Markdown，IDL 只描述查询/命令 API；或
   - B. 建立 `economy.idl.yaml` / `world_rules.yaml`，把经济 operation 与参数机器化；或
   - C. 将经济参数并入 `game_api.idl.yaml` 的 limits/economy section。
2. 不论选择哪项，必须清理所有旧口径：固定 50% Recycle、0.1%/tick StorageTax、浮点费率示例。
3. `D3` 的 lifespan refund 10–50% 与 `D4` 的 0/1/5/20bp tier 必须在被选定权威源中唯一出现，其他文档只引用。

## CrossCheck 补漏发现（基于本轮 CrossCheck）

本轮无 Phase 2；以下为 Phase 1 报告中提出并已纳入上方结论或维护项的 CrossCheck：

### CX1: `auth_api.idl.yaml` 缺失 / Auth API 机器源不明
**来源**: rev-dsv4-apidx, rev-gpt-apidx, rev-dsv4-security, rev-gpt-security, rev-gpt-architect  
**发现**: 任务/文档引用 `specs/reference/auth_api.idl.yaml`，但文件不存在。Auth 工具若已合并到 `game_api.idl.yaml`，合并不完整；若未合并，则机器源缺失。  
**处置**: 升级为 B19-2 的一部分。

### CX2: `design/architecture.md` 与 `specs/gameplay/04-replay-recording.md` 缺失
**来源**: rev-dsv4-determinism, rev-gpt-determinism  
**发现**: 任务授权列表中存在这些文件名，但 R19 review copy 中不存在。  
**处置**: 文档维护项。若已合并到 `design/engine.md` / `01-tick-protocol.md` / `05-persistence-contract.md`，需更新导航和评审输入清单；若未合并，需恢复集中 spec。

### CX3: `terminal_state` / `wasm_status` / replay integrity state 命名分叉
**来源**: rev-gpt-architect, rev-gpt-determinism, rev-gpt-performance  
**发现**: IDL 的 `terminal_state` 是 WASM execution terminal state；persistence/engine 中仍有 `verified/audit_gap/unreplayable/reconstructable` 被写成 terminal_state 或保留 `wasm_status`。  
**处置**: 记录为方向 High（见 T-H1），未达到跨模型共识 Blocker，但需修复。

### CX4: soft_launch 三阶段 PvP 证据不一致
**来源**: rev-dsv4-designer, rev-gpt-architect 报 GAP；rev-gpt-designer, rev-dsv4-architect 报 CLOSED。  
**发现**: 详细章节存在三阶段描述，但部分表格/授权文件只出现 binary 1500 tick soft_launch。  
**处置**: 记录为 Medium：清理旧表格并加权威锚点即可。

## 逐项闭合汇总

| ID | R19 Speaker 判定 | 共识强度 | 主要依据 |
|---|---|---:|---|
| B1 YAML vs Markdown 双写不一致 | **GAP** | 高 | API/DX 双模型 + Designer 双模型 + Performance/Economy/Security GPT 均发现派生文档漂移 |
| B2 RejectionReason 未闭合 | **PARTIAL / GAP** | 高 | 主源 35 canonical 已闭合；旧 wire code 未传播清理 |
| B3 MCP Tool 三套名称空间 | **GAP** | 高 | API/DX 双模型 + Designer 双模型 + Security GPT |
| B4 Tick/Trace/Persistence 分叉 | **PARTIAL / HIGH** | 中 | GPT Architect/Determinism/Performance 指出 `terminal_state` 与调度残留；DSV4 多数判 CLOSED |
| B5 安全字段未入机器源 | **PARTIAL / GAP in Auth scope** | 中高 | Active 46 tools 有安全列；Auth 工具缺机器源由 Security GPT 强烈指出 |
| B6 经济单源未闭合 | **PARTIAL / D-item needed** | 中高 | DSV4 Economy 判 CLOSED；GPT Economy/Determinism/Performance/API 判机器源未闭合 |
| B7 容量合同不可证明 | **GAP** | 高 | worker pool 256 vs 1000 被 Architect/Determinism/Performance 多方向确认 |
| D1 api-registry.md 全量生成 | **CLOSED with caveat** | 高 | 主 registry 声明生成并覆盖 11 sections；仍需生成校验防 drift |
| D2 RejectionReason canonical+debug_detail | **PARTIAL** | 高 | YAML/API Registry closed；派生文档未清，归入 B19-1 |
| D3 Recycle refund lifespan 10–50% | **GAP / stale docs** | 高 | Economy DSV4 认为 RL closed；Designer 双模型、GPT Economy/Performance 指出固定 50% 残留或未机器化 |
| D4 Storage tax 0/1/5/20bp | **PARTIAL / GAP** | 中高 | RL/gameplay 有定义；snapshot/IDL/ResourceOperation 未闭合或旧平税率残留 |
| D5 blob 异步上传 | **CLOSED** | 高 | API/DX、Architect、Determinism、Performance、Security 多方向确认 |
| D6 soft_launch 3-stage PvP | **PARTIAL / Medium** | 中 | 有详细三阶段段落，但旧 binary 1500 tick 表述仍误导 |
| DA1 deploy_mutation replay_class | **GAP** | 高 | Security 双模型一致；Performance GPT 同意 |
| DA2 f64→fixed-point | **GAP** | 很高 | API/DX 双模型 + Architect 双模型 + Determinism 双模型 + GPT Economy/Performance |
| DA3 worker pool 256 default | **GAP** | 高 | IDL 值为 256，但 engine 推导仍 1000；与 B7 合并处理 |

## 残留 GAP（按修复优先级）

1. **P0 — 生成源/派生文档漂移**：RejectionReason、MCP tools、Auth tools、error envelope、host function examples、capacity examples 仍在多处双写。
2. **P0 — DA2 f64**：IDL 仍有 11 类 `f64` 字段，必须 fixed/int/string 化或明确 display-only 并从 canonical/replay 路径排除。
3. **P0 — deploy replay_class**：`swarm_deploy` 不能同时是 `idempotent_mutation` 字段值与 `deploy_mutation` 机制说明。
4. **P0 — worker pool capacity**：256 与 1000 的关系必须建模并重算，否则 B7/DA3 不闭合。
5. **P1 — 经济机器源边界**：Resource Ledger 是否足以作为权威源需要用户裁决；若要求机器闭合，应新增/扩展 YAML。
6. **P1 — TickTrace/Persistence 命名**：`terminal_state` 应只表示 WASM execution terminal state；replay/blob integrity state 应改名。
7. **P1 — soft_launch / Recycle / StorageTax 旧表格**：详细章节有新机制，但旧简表仍误导，需要删除或改为引用权威源。
8. **P2 — 评审输入清单维护**：删除或恢复 `auth_api.idl.yaml`、`architecture.md`、`04-replay-recording.md` 等路径引用。

## 方向专属 High 优先级

### A-H1: TickTrace / Persistence 状态机双语义
- 来源：rev-gpt-architect, rev-gpt-determinism, rev-gpt-performance
- 处置：High。将 persistence 的 `verified/audit_gap/unreplayable/reconstructable` 改名为 `trace_integrity_state` / `replay_blob_state`，删除 `wasm_status` 残留。

### S-H1: Auth API 机器源缺口
- 来源：rev-gpt-security, rev-dsv4-security（缺失文件记录）
- 处置：High。明确 `auth_api.idl.yaml` 是否存在；Auth 工具必须有机器可校验安全列。

### D-H1: Recycle 与 soft_launch 的旧口径破坏玩法闭合
- 来源：rev-dsv4-designer, rev-gpt-designer
- 处置：High/Medium。Recycle lifespan 公式必须替换固定 50%；soft_launch 旧 binary 表格必须引用三阶段权威段落。

### P-H1: 256-worker 下容量推导需重算
- 来源：rev-dsv4-performance, rev-gpt-performance
- 处置：High。重算 500/1000 active players、queue depth、fair-share、deadline、degraded mode。

### E-H1: 经济规则是否机器化需裁决
- 来源：rev-gpt-economy vs rev-dsv4-economy 分歧
- 处置：High。见 D-item U2。

### X-H1: API Registry 主链路闭合但旁路文档仍会误导 SDK/MCP 实现者
- 来源：rev-dsv4-apidx, rev-gpt-apidx
- 处置：High。非权威文档不得列完整工具/错误码表。

### T-H1: replay recording 集中 spec 缺失
- 来源：rev-dsv4-determinism, rev-gpt-determinism
- 处置：Medium/High。若 replay recording 已分散到其他文件，更新导航；否则恢复 spec。

## Medium/Low 处置

| ID | 问题 | 来源方向 | 处置 |
|---|---|---|---|
| M1 | `MAX_PATH_LENGTH` 100 vs 500 | rev-dsv4-performance | Medium：以 IDL/API Registry 500 为准，清理 `02-command-validation.md` 旧值 |
| M2 | `pids.max` 32 vs 16 | rev-dsv4-performance | Medium：同一 `wasm-sandbox.md` 内统一 OS hardening 表 |
| M3 | EXECUTE budget 400ms target vs 500ms timeout | rev-dsv4-performance, rev-gpt-performance | Low/Medium：标注 target vs timeout，不作 blocker |
| M4 | `resources/list` / `resources/read` 非 `swarm_*` namespace | rev-gpt-designer | Medium：若保留，需在 gateway/security docs 明确 namespace policy |
| M5 | `WorldEntityCapReached` 未注册 canonical RejectionReason | rev-gpt-designer | Medium：改为已有 canonical code 或注册新 code |
| M6 | `design/gameplay.md` 仍有小数费率 `0.01/0.05` | rev-gpt-economy | Medium：改为 bp 或引用 Resource Ledger |
| M7 | pathfinding fair-share 100 nodes/player/tick 可能 UX 偏紧 | rev-gpt-performance | Low：性能安全，留给玩法/UX 调参 |

## D-items（需用户裁决）

### U1: Auth API 机器源采用独立 `auth_api.idl.yaml` 还是并入 `game_api.idl.yaml`？

**问题**: 多个文档/任务引用 `auth_api.idl.yaml`，但文件不存在；`design/auth.md` 中大量 Auth MCP tools 未进入 `game_api.idl.yaml`。

**选项**:
- A. 新增 `specs/reference/auth_api.idl.yaml`，Auth 生命周期工具由它生成。
- B. 明确 Auth 已合并到 `game_api.idl.yaml`，并把完整 Auth tool surface 纳入该文件。

**推荐**: B。减少 IDL 源数量，避免 API Registry 再次分叉；但必须补齐 Auth 工具和安全列。

### U2: 经济权威源是否必须机器可读？

**问题**: rev-dsv4-economy 认为 `08-resource-ledger.md` 已是唯一经济权威；GPT Economy/Determinism/Performance 认为 R19 约束下 IDL/YAML 才是机器源，经济公式未机器化则 B6/D3/D4 未闭合。

**选项**:
- A. 接受 `08-resource-ledger.md` 作为经济权威 Markdown，IDL 只描述 API 查询与命令。
- B. 新增 `economy.idl.yaml` / `world_rules.yaml`，机器化 ResourceOperation 与参数。
- C. 扩展 `game_api.idl.yaml`，在其中加入 economy section。

**推荐**: B。经济规则变化频繁且属于 world rules，用独立机器源比塞入 game API 更清晰；`api-registry.md` 可引用该源生成经济章节摘要。

### U3: worker pool 的 `256` 与 `1000` 是否分别表示 default 与 hard cap？

**问题**: 如果 256 是 default、1000 是 hard cap，则不是数值冲突，但当前文档未建模两个字段；如果二者都表示 max_pool，则冲突。

**选项**:
- A. `worker_pool_default = 256`, `worker_pool_hard_cap = 1000`，两者都进入 IDL limits。
- B. 统一为单值 `worker_pool_max = 256`，删除 1000-worker 推导。

**推荐**: A，但必须重算默认 256 下的容量场景，并把 hard cap 1000 标为可选配置上限而非默认证明基础。

### U4: `deploy_mutation` 是 replay_class 枚举值还是 deploy mechanism 名称？

**问题**: 当前文档同时使用二者，造成安全实现歧义。

**选项**:
- A. `deploy_mutation` 成为正式 replay_class。
- B. 保持 `idempotent_mutation` replay_class，但新增 `mutation_mechanism: deploy_mutation` 并明确防重放使用 FDB version_counter，不使用 Dragonfly nonce。

**推荐**: A。R18 DA1 已按“deploy_mutation replay_class”追踪，且安全 reviewer 一致认为这是防重放语义边界。

## 文档维护项

1. 更新评审输入清单：移除不存在或已合并的 `auth_api.idl.yaml`、`design/architecture.md`、`specs/gameplay/04-replay-recording.md`；或恢复这些文件。
2. 对 `design/interface.md`、`mcp-tools.md`、`commands.md`、`08-api-idl.md` 标注“非权威，不列完整表；详见 api-registry.md”。
3. 为 `game_api.idl.yaml → api-registry.md` 增加实际生成命令、CI check 和 drift report；目前多名 reviewer 只看到声明，未看到可验证流水线。
4. 建立 stale-reference scan：`wasm_status`、`InsufficientResources`、`Fatigued`、`NotMovable`、`MAX_POOL = 1000`、`0.1%/tick`、`body_cost * 0.5`、`f64`。
5. R20 reviewer prompt 应明确经济源策略、Auth 源策略和 worker pool 语义，避免再次因范围解释不同产生噪声。

## 收敛趋势 R15→R19

- **R15**：14/14 Phase 1 报告完成，Speaker 聚合 7 个共识 Blocker，并创建 4 个 Phase 2 CrossCheck 补充任务。问题仍是大面积架构/API/文档单源不一致。
- **R16**：14/14 Phase 1 报告完成，Speaker 聚合 6 个共识 Blocker，并创建 7 个 Phase 2 CrossCheck。数量略降，但跨方向补漏增加，说明主问题开始从“缺设计”转向“跨文档闭合”。
- **R17**：14/14 报告完成，Speaker 聚合 6 个共识 Blocker、4 个 Phase 1 CrossCheck 补漏发现。YAML/Registry、MCP、经济、容量、Replay 仍是核心轴线。
- **R18**：14/14 报告完成，Speaker 裁决 REQUEST_MAJOR_CHANGES，聚合 7 个共识 Blocker、6 个 D-items；重点结论是 YAML→api-registry 主链路基本闭合，但 API/安全/经济/容量仍需用户裁决与传播修复。
- **R19**：从“设计缺口”进一步收敛为“闭合传播缺口”：主链路已有，但旧 Markdown、旧状态机、旧数值、旧 Auth 工具和 IDL 类型未清理。Blocker 类型更具体，可通过一轮集中生成源/派生文档清理关闭。

趋势判断：**正在收敛，但尚未达到 Freeze**。R19 的剩余问题大多不是重新设计，而是单源建模、生成、旧文档清理和少量用户边界裁决。若按本报告的 P0 项一次性修复，R20 有机会从 REQUEST_MAJOR_CHANGES 降到 CONDITIONAL_APPROVE；若继续只修主 registry 而不清旁路文档，B1/B3/DA2/B7 会继续反复出现。

## 评审统计

### Verdict 矩阵

| Direction | GPT-5.5 | DeepSeek V4 Pro | 方向结论 |
|---|---|---|---|
| Architect | CONDITIONAL_APPROVE | CONDITIONAL_APPROVE | 条件通过，但 DA2/B7/B4/D6 残留 |
| Security | REQUEST_MAJOR_CHANGES | CONDITIONAL_APPROVE | DA1/Auth 源缺口为核心 |
| Designer | REQUEST_MAJOR_CHANGES | REQUEST_MAJOR_CHANGES | B1/B3/D3/D6 残留 |
| Performance | REQUEST_MAJOR_CHANGES | CONDITIONAL_APPROVE | worker pool 256/1000 为核心 |
| Economy | REQUEST_MAJOR_CHANGES | APPROVE | 对“经济权威源是否机器化”存在方向内分歧 |
| API/DX | REQUEST_MAJOR_CHANGES | REQUEST_MAJOR_CHANGES | 派生文档 drift、f64、MCP namespace 为核心 |
| Determinism | REQUEST_MAJOR_CHANGES | CONDITIONAL_APPROVE | f64、worker pool、terminal_state、经济机器源 |

### 数量统计

- APPROVE: 1/14
- CONDITIONAL_APPROVE: 5/14
- REQUEST_MAJOR_CHANGES: 8/14
- REJECT: 0/14

### 共识强度评估

| 问题簇 | 共识强度 | 说明 |
|---|---|---|
| DA2 f64 残留 | 很高 | 两个 API/DX、两个 Architect、两个 Determinism + 多方向 GPT 均指出 |
| B7/DA3 worker pool | 高 | Architect/Determinism/Performance 多方向确认 |
| B1/B2 RejectionReason 传播 | 高 | API/DX + Designer 双模型确认，其他方向补充 |
| B3 MCP/Auth namespace | 高 | API/DX + Designer + Security 确认 |
| DA1 deploy replay_class | 高 | Security 双模型一致，Performance GPT 支持 |
| B6/D3/D4 economy machine source | 中高但有分歧 | DSV4 Economy 判 CLOSED；多个 GPT/技术方向判 GAP |
| B4 terminal_state/state machine | 中 | GPT 多方向指出，DSV4 多方向判 CLOSED |
| D6 soft_launch | 中低 | 有详细章节但旧表格/范围导致 reviewer 分歧 |

## R20 入场条件

R20 不应再次泛化评审，应做定向 closure verification，入场前至少完成：

1. 清理所有非 canonical RejectionReason wire code。
2. 统一 MCP/Auth tool source，并处理 `auth_api.idl.yaml` 缺失。
3. 修正 `swarm_deploy.replay_class`。
4. 消除或显式豁免 IDL 中所有 `f64`。
5. 统一 worker pool default/hard cap 语义并重算 engine capacity。
6. 明确经济机器源策略并清理 Recycle/StorageTax 旧口径。
7. 重命名 replay/blob integrity state，删除 `wasm_status` 残留。

完成以上后，R20 才有实际机会进入 CONDITIONAL_APPROVE / FROZEN 候选状态。
