# Swarm 设计评审 R23 — Speaker 共识报告

## 裁决概要

- Phase 1 完成情况：14/14 份评审报告已在 `/data/swarm/docs/reviews/R23/rev-*-*.md` 落盘；看板父任务中 `R23-gpt-economy` 未记录 result，但原始文件 `/data/swarm/docs/reviews/R23/rev-gpt-economy.md` 存在且已纳入综合。
- Phase 2 补漏情况：本轮未等待 Phase 2 补漏；按 Plan B 原则，Phase 1 完成即启动综合。CrossCheck 项已在本报告中归档，建议作为 R24 或定向补审输入。
- 收敛评估：14 位 reviewer 中 13 位给出 `CONDITIONAL_APPROVE`，1 位给出 `REQUEST_MAJOR_CHANGES`（rev-gpt-economy）。表面多数为条件通过，但 Critical/High 集中在经济可玩性、API/IDL 单事实源、确定性合同、ECS 调度顺序与性能容量证明，仍不满足 Freeze。
- Freeze 状态：未冻结。R23 不能进入大规模实现；可进入“合同收敛 + 经济启动曲线 + 规模证明”修复轮。
- Speaker 立场：本报告只聚合评审共识，不独立新增设计判断。所有 Blocker 均可追溯到至少两个方向、至少两个模型的原始报告。

## 总体 Verdict

REQUEST_MAJOR_CHANGES

理由：虽然多数方向认为总体架构方向正确，但本轮存在 4 组跨方向、跨模型共识 Blocker：经济启动/成长闭环未证明；API/IDL/Registry 单事实源不可信；确定性与执行顺序合同冲突；1000-player/rollback/FDB/pathfinding 的容量证明不足。尤其经济方向出现 1 位 `REQUEST_MAJOR_CHANGES` 且另一模型列出 3 个 Critical，按冻结标准必须先修。

## 共识 Blocker（跨方向 + 跨模型同意）

### B1: World 经济启动与成长闭环未证明
**方向 × 模型矩阵**: Economy/GPT（E1, E3, REQUEST_MAJOR_CHANGES）, Economy/DeepSeek（D1 Critical, D4 High, NE1）, Designer/GPT（G1 第一小时旅程缺口）, Designer/DeepSeek（G3 长期目标与龟缩均衡）, Architect/DeepSeek（WorldConfig 缺 `starting_resources` CrossCheck）。
**问题**: Standard World 在 1/5/20/50 房间示例中均为长期净亏损；文档承认需要初始资源包但未定义 World starting resources、break-even path、RCL/source 升级曲线或启动补贴反小号约束。若照文实现，新玩家可能在 safe/soft_launch 期间仍因 upkeep deficit 进入效率惩罚与死亡螺旋。
**修正要求**:
- 为 World/Standard 增加权威 `starting_resources` 或 safe-mode upkeep waiver，并写入 world.toml schema / API Registry / Resource Ledger。
- 增加 tick 0→500→2000→RCL3→5 rooms 的 growth path 表，列出 faucet、sink、升级成本、break-even tick。
- 修正 balance sheet 的收入侧假设：Controller income、Source level、Harvester 效率、PvE budget、allied transfer 是否计入当前闭环必须显式声明。
- 若 1-room Standard 仍设计为净亏损，必须给出补贴额度、补贴持续 tick、反 smurf 约束与 UI/MCP 预警合同。

### B2: API/IDL/Registry 单事实源未冻结
**方向 × 模型矩阵**: API/DX/GPT（X1-X4）, API/DX/DeepSeek（C1-C4, H1-H3）, Architect/GPT（A1, A8）, Economy/DeepSeek（D2, D9）, Security/GPT（H1 auth 双轨）。
**问题**: Registry、codegen、host-functions、commands、mcp-tools、interface 等文档在工具数量、CommandAction 数量、RejectionReason 数量、host function ABI、Command JSON shape、错误 envelope、Auth tool schema 上出现多处冲突。该问题直接破坏 SDK/codegen、MCP client、WASM import stub 与错误处理稳定性。
**修正要求**:
- 明确 IDL YAML 为唯一机器源；Registry 与 reference 文档必须生成或标注不可手写区，CI diff 为零。
- 统一 `host_get_terrain`、`host_path_find`、`host_get_world_rules` 等 ABI；非权威讲解文档不得重列过期签名。
- 明确 `CommandIntent` envelope：`object_id` 位于顶层还是 action 参数内，并让所有 CommandAction builder 可生成正确类型。
- 统一 MCP/tool/CommandAction/RejectionReason 计数；删除或降级旧错误码到 `debug_detail`，不得出现在 wire enum 语境。
- 统一 JSON-RPC error envelope：数字 `error.code` 与字符串业务码不可并存；Auth 同名双 schema 必须合并或分 profile 命名。

### B3: 确定性执行合同仍存在互相冲突的权威定义
**方向 × 模型矩阵**: Determinism/GPT（T1-T4 High）, Determinism/DeepSeek（D1 Critical, D3-D4 High）, Architect/GPT（A2-A4）, Architect/DeepSeek（D1 Critical, D4 Medium）, API/DX/GPT（X8, X7）, Performance/GPT（rollback/snapshot concerns）。
**问题**: TickTrace replay-critical 边界、`terminal_state` 语义、特殊攻击优先级、status writer、system order、snapshot truncation、WASM output size/行为、seed/shuffle formula、SIMD 默认策略等存在多版本定义。只要不同实现选择不同文档，即可造成 replay 分叉、state checksum 分叉或审计误判。
**修正要求**:
- 拆分 `execution_terminal_state` 与 `trace_integrity_state`，并在 TickTrace、Persistence、API Registry 统一命名。
- 明确 FDB 内最小 replay trace：canonical commands、rejections、fuel ledger、activation decisions、manifest hashes、state checksum 必须原子提交；对象存储只保存 rich/debug trace。
- 以 `06-phase2b-system-manifest.md` 或新的机器 manifest 为唯一 system order/status writer 权威，移除 02 中重列的冲突顺序。
- 统一特殊攻击优先级，纳入 action/world manifest hash；S16-S21 与 S22 的写入权限二选一。
- 建立单一 Visibility/Truncation Manifest，定义 bucket、距离、tie-break、serialization order，并绑定 `visibility_truncation_hash`。
- World 默认禁用 WASM SIMD，或明确 SIMD 架构绑定 replay 策略；推荐默认禁用，显式 opt-in deterministic subset。

### B4: 规模性能与 rollback/FDB 容量证明不足
**方向 × 模型矩阵**: Performance/GPT（P1-P2）, Performance/DeepSeek（H1-H3, M1）, Architect/GPT（A5-A6）, Architect/DeepSeek（D3, D6）, Determinism/DeepSeek（entity allocator restore）, Security/DeepSeek（pathfinding fair-share abuse）。
**问题**: 1000-player 场景、worker pool 256/1000 假设、cgroup/fuel/CPU admission、Phase 2a 100k commands 串行循环、Bevy World 每 tick 深拷贝 rollback、FDB 单事务热区、pathfinding 100k nodes fair-share 都缺少可验证容量证明。现有文本更像目标而非 evidence-backed contract。
**修正要求**:
- 重新推导 500/1000 active players 下的 worker pool、CPU token、fuel admission 模型，默认值与 hard cap 必须一致。
- 增加 synthetic benchmark 要求：100k command validate/apply、50k entity snapshot clone/restore、1000×256KB snapshot stitching、FDB commit p99/conflict rate、50×50 A* nodes distribution。
- 证明 Bevy snapshot/restore 覆盖 entity ID allocator 与 spawn.energy 等所有 rollback-critical resource/component，或改为 undo-log/CoW。
- 给出 FDB key layout 与 conflict range 策略；评估按 room partition 的事务方案。
- 上调或重构 pathfinding budget：per-room cache、flow-field、connectivity precheck、player-visible budget API，以及 anti-smurf/fair-share abuse 处理。

## CrossCheck 补漏发现（基于 Phase 2）

本轮没有实际执行 Phase 2 补漏任务，因此无 Phase 2 新发现。Phase 1 CrossCheck 聚类如下，建议作为 R24 定向补审或修复后复核清单：

### CX1: IDL/codegen/registry 单事实源链路
**来源**: API/DX、Architect、Designer、Economy 多方向 → 目标方向: Architect / API-DX
**发现**: 工具数量、CommandAction、RejectionReason、host ABI、Command shape、storage/build cost 均出现派生文档漂移。
**处置**: 已升级为 B2。

### CX2: 资源账本、WorldConfig 与经济可玩性
**来源**: Economy、Designer、API/DX → 目标方向: Architect / Economy / Designer
**发现**: `starting_resources` 缺失、World Standard 净亏损、upkeep/tax/refund/build cost 多源不一致。
**处置**: 已升级为 B1，并与 B2 部分重叠。

### CX3: replay-critical 持久化边界与 rollback
**来源**: Determinism、Performance、Architect、Security → 目标方向: Architect / Determinism
**发现**: FDB 最小 replay trace、对象存储 rich blob、Bevy snapshot/restore、entity allocator、spawn.energy rollback 未形成单一可测合同。
**处置**: 已升级为 B3/B4。

### CX4: 安全认证与 transport profile
**来源**: Security/GPT、API/DX/GPT、Security/DeepSeek → 目标方向: Security / API-DX
**发现**: Auth API 双轨、同名 auth tool schema、WS 每消息签名、Dragonfly nonce、CSR challenge、Refresh token grace 需要收敛。
**处置**: 记录为方向 High；其中 Auth schema 漂移进入 B2。

### CX5: Gameplay 体验与可学习性
**来源**: Designer/GPT、Designer/DeepSeek、Economy/GPT → 目标方向: Designer / API-DX
**发现**: 第一小时旅程、AI-only onboarding、World rule card、长期非资源目标、特殊攻击解锁曲线需要产品化验收。
**处置**: 记录为方向 High/Medium；未升级为 Freeze Blocker，但应进入 R24 修复计划。

## 方向专属 High 优先级

### A-H1: `terminal_state` 与 replay/audit 字段命名拆分
来源：rev-gpt-architect A2、rev-gpt-determinism T2。处置：进入 B3。

### A-H2: 特殊攻击 reducer/status writer 多路径写入
来源：rev-gpt-architect A3、rev-gpt-determinism T3/T4、rev-dsv4-architect D1。处置：进入 B3。

### A-H3: per-player drone cap 与 RCL room capacity 语义冲突
来源：rev-dsv4-architect D2、Designer CrossCheck。处置：High，需用户/Gameplay 决定 cap 语义。

### S-H1: Auth 双轨、Admin 权限、WS 签名与 nonce/replay
来源：rev-gpt-security H1-H4、rev-dsv4-security S-H1/S-H2/S-H4。处置：High；Auth schema 部分进入 B2。

### S-H2: CVE/Wasmtime/security_epoch 运营门禁
来源：rev-gpt-security H5、rev-dsv4-security S-H5、Performance M4。处置：High；补 CI fail-closed、epoch bump 编译风暴 runbook。

### D-H1: First-hour Quest Spine 与 AI-only onboarding
来源：rev-gpt-designer G1/G2、rev-dsv4-designer G3/G5。处置：High；未阻塞核心合同，但阻塞“可玩性验收”。

### D-H2: Disrupt 反制面与 Controller 免费维修龟缩均衡
来源：rev-dsv4-designer G1/G2。处置：High；需参数/机制 A/B 裁决。

### P-H1: Worker pool / cgroup / fuel admission 模型
来源：rev-gpt-performance P1、rev-dsv4-performance H1、rev-dsv4-architect D6。处置：进入 B4。

### P-H2: FDB 单事务热区与 Phase 2a 串行命令瓶颈
来源：rev-gpt-performance P1/P2、rev-dsv4-performance H2、rev-gpt-architect A5。处置：进入 B4。

### E-H1: Storage tax / recycle / build cost / resource formula 冲突
来源：rev-gpt-economy E2/E4/E7、rev-dsv4-economy D2/D3/D6/D9。处置：B1/B2 双重覆盖。

### X-H1: Host ABI、Command shape、错误 envelope、工具计数
来源：rev-gpt-apidx X1-X4、rev-dsv4-apidx C1-C4/H1-H3。处置：进入 B2。

### T-H1: SIMD、RNG、snapshot truncation、WASM output size
来源：rev-gpt-determinism T5/T8、rev-dsv4-determinism D1/D2/D4。处置：SIMD 与 truncation 进入 B3；seed 前向可推导记录为已接受风险但需 runbook。

## Medium/Low 处置

| ID | 问题 | 来源方向 | 处置 |
|----|------|---------|------|
| M1 | API deprecation / semver / min_engine_version 未定义 | API/DX | 合同维护项，随 B2 修复 |
| M2 | MCP 输出 schema 非结构化 | API/DX | SDK/codegen 后续任务 |
| M3 | Rhai mod API 不可见 | API/DX / Architect | 新增 reference 或 Registry section |
| M4 | Snapshot truncation rich-get-richer / visibility DoS | Performance / Security | 加入 truncation manifest 与 abuse tests |
| M5 | TickTrace 10MB buffer 上限接近高负载边界 | Performance | perf gate 与降级策略 |
| M6 | active_aging 10% 过轻 | Economy / Designer | 参数调优项，不阻塞合同冻结 |
| M7 | PvE 30% 预算缺少经验校准 | Designer / Economy | 上线后观测 runbook，先保留可配置 |
| M8 | Long-term identity / community sharing / spectator product contract | Designer | 产品范围项，进入 MVP/Phase 1 取舍 |
| L1 | Fog-of-war 主动侦察机制不足 | Designer | Future RFC |
| L2 | Worker rolling replacement jitter | Performance | 实现细节优化 |
| L3 | HTTP traffic analysis / email multi-account listing | Security | 文档威胁说明与配置开关 |
| L4 | Balance sheet assumption table 缺失 | Economy | 修复 B1 时补齐 |

## D-items（需用户裁决）

### D1: World 新手启动经济采用补贴还是免 upkeep
**问题**: Standard World 当前无 starting resources 且 1-room balance sheet 为负。
**选项**:
- A: 增加 `starting_resources`，并给出补贴耗尽前的 break-even path。
- B: safe_mode 期间免 upkeep / tax，保护期结束前要求玩家达到自维持。
**推荐**: A+B 的弱组合：给最小启动资源，同时 safe_mode 只免部分 upkeep。这样既能防 death spiral，也不会让小号无限免费存活。

### D2: Drone cap 语义是 global per-player 还是 per-room/per-RCL
**问题**: `MAX_DRONES_PER_PLAYER=50` 与 RCL 表 50–500 “最大房间 drone”冲突。
**选项**:
- A: 50 是每玩家全局 cap，RCL 表改为 room total / world capacity 说明。
- B: 50 是 per-room per-player baseline，RCL 表定义 room-level total 或 per-controller contribution。
**推荐**: B。编程 MMO 的成长更依赖 room/RCL 扩张，global 50 会削弱长期成长；但必须明确每房间、每玩家、每世界三层 cap。

### D3: Disrupt 反制范围如何收敛
**问题**: Disrupt 低成本反制 Hack/Drain/Debilitate，可能同质化防御策略。
**选项**:
- A: Disrupt 需要 body part match 或目标状态类型 match。
- B: 保持广谱，但提高 CD/成本或改为概率/强度对抗。
**推荐**: A。机制语义更清楚，也保留不同 body build 的 counterplay。

### D4: Controller repair 免费范围是否保留
**问题**: 免费维修可能提高龟缩均衡，削弱扩张/进攻动机。
**选项**:
- A: 降低全局 cap 到 30–35%，并加入距离衰减。
- B: 保留 50%，但增加进攻方 expedition support / depot bonus。
**推荐**: A。直接降低防守垄断强度，文档修改更小。

### D5: World 默认 SIMD 策略
**问题**: Determinism/DeepSeek 将 World 默认 SIMD=true 评为 Critical。
**选项**:
- A: World/Arena 默认均禁用 SIMD，仅允许 deterministic subset opt-in。
- B: 允许 SIMD，但 TickTrace 绑定 arch/wasmtime target，跨架构 replay 要求同构。
**推荐**: A。Swarm 的核心卖点是 replay/determinism，默认应保守。

### D6: FDB 单事务是否允许作为 Phase 1 默认
**问题**: 性能与架构方向质疑单事务在 500/1000 players 下的热区和大小上界。
**选项**:
- A: 保留单事务 MVP，但明确仅支持小规模并加 perf gate。
- B: 现在就把 room-partition transaction 纳入 Phase 1 合同。
**推荐**: A。先以可实现 MVP 收敛 deterministic kernel，但必须把 500/1000 player 目标降为 benchmark-gated，而非承诺。

## 文档维护项

- 清理或生成所有手写计数：MCP tools、CommandAction、RejectionReason、Auth tools、Host functions。
- 建立“权威源层级”表：IDL YAML / world.toml schema / system manifest / resource ledger / generated registry 各自负责哪些字段。
- 将 `host-functions.md`、`commands.md`、`mcp-tools.md` 中的签名和 schema 改为 generated snippet 或引用 Registry。
- 将 Resource Ledger 公式、economy balance sheet、gameplay 经济说明、api-registry economy limits 全部重跑一致性检查。
- 新增或抽出机器可读 manifests：`SystemScheduleManifest`、`VisibilityTruncationManifest`、`ActionPriorityManifest`、`RngDecisionManifest`。
- R24 前建议先做文档修复，不建议直接启动实现；修复后应以 closure verification 模式验证 B1-B4。

## 评审统计

### Verdict 矩阵

| Direction | GPT-5.5 | DeepSeek V4 Pro | Speaker 归纳 |
|-----------|---------|-----------------|--------------|
| Architect | CONDITIONAL_APPROVE | CONDITIONAL_APPROVE | 架构方向正确，但 system order / terminal_state / capacity contracts 未冻结 |
| Security | CONDITIONAL_APPROVE | CONDITIONAL_APPROVE | 无 Critical，但 auth/WS/Admin/nonce/CVE 需收敛 |
| Designer | CONDITIONAL_APPROVE | CONDITIONAL_APPROVE | 策略空间成立，但第一小时、Disrupt、Controller repair 需修 |
| Performance | CONDITIONAL_APPROVE | CONDITIONAL_APPROVE | 规模目标缺 benchmark 与容量证明 |
| Economy | REQUEST_MAJOR_CHANGES | CONDITIONAL_APPROVE | 本轮最弱方向；World 启动经济和公式一致性阻塞 Freeze |
| API/DX | CONDITIONAL_APPROVE | CONDITIONAL_APPROVE | 单事实源与 codegen 合同未可信冻结 |
| Determinism | CONDITIONAL_APPROVE | CONDITIONAL_APPROVE | 基础好，但多处冲突会造成 replay 分叉 |

### Severity 概览

| Direction | Critical | High | 备注 |
|-----------|----------|------|------|
| Architect | 1 | 6+ | system order、terminal_state、snapshot、cap、rollback |
| Security | 0 | 10 | 两模型各 5 High，集中在 auth 与 operational security |
| Designer | 0 | 4 | 第一小时/MCP 自举/Disrupt/Controller repair |
| Performance | 0 | 6 | worker/FDB/pathfinding/command loop/rollback |
| Economy | 3+ | 6+ | GPT 给 REQUEST_MAJOR_CHANGES；DeepSeek 给 3 Critical |
| API/DX | 4 | 6 | DeepSeek API/DX 给 4 Critical，GPT 同向确认 |
| Determinism | 1 | 7 | SIMD Critical；GPT 列 4 High 合同冲突 |

### 共识强度评估

- B1 经济启动闭环：强共识。Economy 双模型直接命中，Designer 与 Architect CrossCheck 支持。
- B2 API 单事实源：极强共识。API/DX 双模型 + Architect + Economy + Security 均发现派生漂移。
- B3 确定性合同冲突：强共识。Determinism 双模型 + Architect 双模型均命中。
- B4 性能容量证明：中强共识。Performance 双模型直接命中，Architect/Security/Determinism 提供支撑。
- 总体结论：R23 不是概念失败，而是“准实现规范未收敛”。建议先修 B1-B4，再开启 R24 closure verification。
