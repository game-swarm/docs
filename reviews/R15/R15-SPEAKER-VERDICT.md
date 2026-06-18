# Swarm 设计评审 R15 — Speaker 共识报告

## 裁决概要
- 本轮采用 Plan B 两级阅读：Phase 1 已完成 14/14 reviewers（7 方向 × 2 模型），无缺位；本报告基于 Phase 1 立即综合，不等待 Phase 2。
- 收敛评估：设计方向仍被多数评审认可，但文档已从“设计哲学争议”回到“可实现合同冲突”层面；Architecture、Security、API/DX、Determinism 均有 REQUEST_MAJOR_CHANGES，说明 R15 不具备 Freeze 条件。
- Freeze 状态：NOT FROZEN。主要阻塞集中在权威合同重复、ECS/排序确定性、API/Schema 事实源、安全授权矩阵、性能容量合同与经济反雪球参数。
- Phase 2 补漏情况：CrossCheck 项显著超过阈值，已创建 4 个补充任务：Architect `t_edd95fd4`、Security `t_cd4ac48d`、Designer `t_d126e33e`、Determinism `t_ad00e48d`。Phase 2 发现应作为追加项合并到最终裁决或 R15.1 修订清单。

## 总体 Verdict
REQUEST_MAJOR_CHANGES

理由：14 份报告中 6 份给出 REQUEST_MAJOR_CHANGES（GPT Architect、DSV4 Architect、GPT Security、GPT API/DX、DSV4 API/DX、GPT Determinism），其余 8 份均为 CONDITIONAL_APPROVE，没有 APPROVE。多个 Critical/High 问题由 ≥2 方向且 ≥2 模型独立提及，满足共识 Blocker 条件。

## 共识 Blocker (跨方向 + 跨模型同意)

### B1: 权威合同重复且冲突，当前文档不具备实现唯一性
**方向 × 模型矩阵**: Architect(GPT/DSV4), Determinism(GPT/DSV4), API/DX(GPT/DSV4), Performance(GPT/DSV4)
**问题**: 多个核心合同在 design 与 specs 中同时定义且互相冲突：Command 数量/字段、Move 4/8 方向、RejectionReason 命名集合、MCP 工具清单、budget 上限、TickTrace/WAL 语义、ECS chain。实现者必须自行选择“哪个文档为真”，会导致 SDK、引擎、回放验证和运维工具分叉。
**修正要求**: 指定每类合同的唯一事实源：Command/API 以 `game_api.idl` 或等价机器可读 schema 为准；ECS 以单一 Phase 2b System Manifest 为准；错误码以唯一 `RejectionReason` registry 为准；预算上限以统一 capacity contract 为准。其他文档只能引用，不得重新声明可冲突表格。

### B2: ECS Phase 2b 顺序与并行边界自相矛盾
**方向 × 模型矩阵**: Architect(GPT/DSV4), Determinism(GPT), Performance(GPT), Performance(DSV4)
**问题**: engine.md、01-tick-protocol.md、02-command-validation.md 对 `regeneration`、`combat`、`status_advance`、`aging`、`decay`、`spawning_grace` 的相对位置给出互斥定义；部分文档说 parallel set，另一些代码示例把 19/20 个系统 `.chain()`。DSV4 Architect 还指出 `status_advance_system` 与 `aging_system` 在权威链中缺失，会造成特殊攻击永不过期、drone 不衰老。
**修正要求**: 写出唯一 Phase 2b System Manifest，列出每个 system 的 position、reads/writes、must-before/must-after、DeathMark 过滤规则、是否可并行。所有示例代码、流程图、spec 表格必须从该 manifest 派生；补入 `status_advance_system` 与 `aging_system`，并解决 RoomCap 中间态与 `pvp_block_system` 位置冲突。

### B3: 命令排序键与 replay determinism 冲突
**方向 × 模型矩阵**: Determinism(GPT/DSV4), Architect(GPT), API/DX(GPT), Performance(DSV4)
**问题**: `01-tick-protocol.md` 使用 `(priority_class, shuffle_index, sequence, source)`，而 `02-command-validation.md` 使用 `(priority_class, shuffle_order, source, sequence)`；source rank 与 per-source sequence 的关系未统一。同一玩家同 tick 多 source 命令会产生不同执行序，进而改变资源竞争、cooldown、refund、RejectionReason、state_checksum。
**修正要求**: 固定唯一排序键并写入 TickTrace schema、validation pipeline、replay verifier、SDK docs。建议至少包含稳定 tie-breaker：`(priority_class, shuffle_index, source_rank, sequence, command_hash)` 或等价方案；不得依赖输入容器顺序或稳定排序副作用。

### B4: API/SDK/MCP schema 不可生成，developer-facing 合同未闭合
**方向 × 模型矩阵**: API/DX(GPT/DSV4), Architect(GPT), Security(GPT), Determinism(GPT)
**问题**: GPT/DSV4 API/DX 双模型均判定 REQUEST_MAJOR_CHANGES。关键问题包括：MCP 工具缺少逐工具 input/output/error schema；Command enum 跨文档数量与字段不一致；`RejectionReason` 三套命名；`SendMessage` 仅在 interface.md 一行出现且无校验；Host function 仍暴露裸 i32/magic number；IDL 格式与生成路径未形成许可范围内的自洽合同。
**修正要求**: 建立 machine-readable API registry：CommandAction、Command fields、MCP tools、HostFunction、RejectionReason、Error namespace、limits、examples 均由同一 schema/IDL 生成或引用。补齐 MCP 关键工具 schema，删除/冻结无校验指令，统一 `RejectionReason` 命名并提供迁移表。

### B5: 安全授权/沙箱/认证合同不足以证明边界
**方向 × 模型矩阵**: Security(GPT/DSV4), API/DX(GPT), Determinism(GPT), Performance(DSV4)
**问题**: 安全方向双模型指出多处 High/Critical：WebSocket 握手后长期免签放大连接劫持风险；MCP/REST 授权矩阵不是完整规范；sandbox OS 隔离配置互相矛盾；admin challenge “无状态”与一次性消费矛盾；Deploy 防重放 spec 内矛盾；Server Intermediate CA 私钥在线暴露；host functions 缺少 per-tick 上限。
**修正要求**: 写出唯一机器可读授权矩阵，未列方法默认拒绝注册；WebSocket mutation/debug/admin 必须有 per-message envelope 或固定只读 subscription 约束；sandbox profile 统一 namespace/seccomp/cgroup/pids/io 数值；admin-critical challenge 必须 FDB 事务内一次性消费或 monotonic counter；Intermediate CA 私钥应引入离线/短期签发/HSM 或明确风险接受边界。

### B6: 性能容量合同与硬上限数学不一致
**方向 × 模型矩阵**: Performance(GPT/DSV4), Architect(GPT/DSV4), Determinism(GPT), Security(GPT)
**问题**: 两位 Performance 均未 APPROVE。硬上限组合（1000 players × 1000 commands/tick、path_find 100M nodes/tick 理论上限、每玩家 2500ms sandbox deadline、Arena 300ms tick、Bevy World 深拷贝）与 3s World tick / 300ms Arena tick 不匹配。FDB 单事务与 world-head 热点也未给出 key layout/conflict range/事务大小目标。
**修正要求**: 将“单玩家 hard cap”改为全局 tick budget + per-player fair share，超限 deterministic reject；定义 pathfinding global/per-room budget；给出 fuel→wall-clock p99 校准；明确 rollback snapshot 采用 delta/COW/double-buffer 而非无条件 deep copy；FDB head commit 只写小 manifest/hash/pointer，并给出 p99 事务大小目标。

### B7: 经济反雪球默认值与资源转移规则未闭合
**方向 × 模型矩阵**: Economy(GPT/DSV4), Designer(DSV4), Performance(GPT), Security(GPT)
**问题**: Economy 双模型均指出 Vanilla 维护费曲线与 anti-snowball 目标不一致：文档声称 O(n²)/超线性，但默认参数几乎线性。allied player↔player transfer 可能绕过物流成本、转换时间、存储税、新玩家资源门；PvE faucet 仅有全局 30% cap，缺少玩家/区域/时间窗预算账本。DSV4 Designer 也指出防守偏置与 PvE/PvP 激励需要调参。
**修正要求**: 产出 Economy Balance Sheet（1/5/20/50 房间，收入、支出、税、维护费、净流量）；统一 empire-upkeep 默认参数与示例曲线；allied transfer 必须落入本地物理物流或全局转账并承担损耗/时间/税务/同源账号限制；PvE drop 增加 global/zone/player/event budget ledger。

## CrossCheck 补漏发现（基于 Phase 2）
Phase 2 已创建但尚未完成；本节记录 Phase 1 CrossCheck 队列，不将其作为等待条件。

### CX1: Architect 补充阅读队列
**来源**: API/DX、Economy、Determinism、Performance、Security → 目标方向: Architect
**发现**: CommandAction/CustomActionRegistry、FDB/TickTrace/WAL、Allied transfer 权威入口、WASM worker pool/IPC、admin validate_and_apply 管线均被跨方向点名。
**处置**: 已创建 `t_edd95fd4`；Phase 2 若确认与 B1/B2/B6 同源，应升级/合并为 Blocker 修订项。

### CX2: Security 补充阅读队列
**来源**: API/DX、Determinism、Performance、Economy、Designer → 目标方向: Security
**发现**: world_seed 生命周期、safe_mode rejection、TLS/明文措辞、economy query 可见性、alliance 洗钱/刷号、host RNG/covert channel 均需安全复核。
**处置**: 已创建 `t_cd4ac48d`；其中授权矩阵、seed 管理、economy abuse 与 B5/B7 高度重叠。

### CX3: Designer/UX 补充阅读队列
**来源**: Performance、API/DX、Economy、Security → 目标方向: Designer
**发现**: snapshot truncation 对战术公平、tick delay/COLLECT 截断体验、opaque error 调试体验、`swarm_simulate` 命名预期、Market/contract/allied transfer MVP 边界需补漏。
**处置**: 已创建 `t_d126e33e`；当前不升级为 Blocker，但可能形成 D-item 或 High。

### CX4: Determinism 补充阅读队列
**来源**: API/DX、Security、Performance、Architect → 目标方向: Determinism
**发现**: dynamic CustomAction registry、simulate/dry-run、host function buffer ABI、negative error code、fuel/host budget 可能影响 replay 稳定。
**处置**: 已创建 `t_ad00e48d`；若确认 registry 可变性进入 replay 输入外，应并入 B3/B4。

## 方向专属 High 优先级

### A-H1: Component 读写矩阵覆盖不足
来源: rev-dsv4-architect D4；rev-gpt-architect A4。当前矩阵仅覆盖约 6 个系统，缺少 controller、repair、room_state、global_storage、cargo、rule module 等系统的 R/W 声明，无法证明 Bevy 并行安全。

### S-H1: WebSocket 与 MCP/REST 授权矩阵必须机器可读
来源: rev-gpt-security H1/H2；rev-dsv4-security C1/H1。逐方法 scope、transport、replay class、rate limit、visibility、audit redaction、CSRF/Origin 必须闭合。

### D-H1: 首小时体验与策略学习资源仍不够产品化
来源: rev-gpt-designer G1/G2；rev-dsv4-designer High/Medium。Golden Path 更像 checklist，不像玩家情绪弧线；AI 规则可学但策略资源不足，应补 first-hour plan、annotated replay、failure cases、self-eval benchmark。

### P-H1: Command/path_find/COLLECT 硬上限必须改为全局容量预算
来源: rev-gpt-performance P1；rev-dsv4-performance C1/C2/C3。当前上限数学不可实现，需要 deterministic admission/reject 与 benchmark contract。

### E-H1: Vanilla Economy Balance Sheet 缺失
来源: rev-gpt-economy E1/E2/E3；rev-dsv4-economy D1-D4。维护费曲线、存储税、allied transfer、PvE faucet 都需要数值表证明闭环。

### X-H1: MCP 工具 schema 与错误 taxonomy 未闭合
来源: rev-gpt-apidx X1-X5；rev-dsv4-apidx D1-D8。无 schema 无法生成 SDK，也无法稳定支持 AI agent 自动修复错误。

### T-H1: RNG 与多 tick 状态机仍有隐式分叉点
来源: rev-gpt-determinism T4/T5；rev-dsv4-determinism D2-D10。seed rotation、draw ordinal、host random API、Room/Hack/Drain/Fortify/Spawn refund 转移表需补齐。

## Medium/Low 处置
| ID | 问题 | 来源方向 | 处置 |
|----|------|---------|------|
| M1 | `active_players` shuffle 前初始排序未指定 | Determinism DSV4 | Medium，纳入 B3 排序合同修订 |
| M2 | Snapshot `distance_to_drone` 参考点模糊 | Determinism DSV4 | Medium，交由 Determinism Phase 2 与 Designer Phase 2 复核 |
| M3 | Recycle refund 使用浮点表达且与定点整数策略冲突 | Architect DSV4 / Determinism DSV4 / Economy DSV4 | Medium，改为 basis points 定点公式 |
| M4 | Controller 升级分类为 Lockup 但更像 Progression Sink | Economy GPT | Medium，经济分类账术语修订 |
| M5 | Tutorial 资产隔离未写成硬约束 | Economy GPT | Medium，补充 Tutorial/World 资产不可转移 |
| M6 | Replay/观战分享产品形态不足 | Designer GPT | Medium，列入 Phase 1+ 产品 backlog |
| M7 | Drone 人格/efficiency 命名可能误导数值含义 | Designer GPT | Low，UI 文案修订 |
| M8 | JSON-RPC SwarmError 共用 `-32000` | API/DX DSV4 | Medium，纳入错误 registry |
| M9 | Arena 无天梯与赛季/league 文案冲突 | Designer GPT | Low/Medium，统一 MVP vs Future 口径 |
| M10 | Wasmtime 版本 pin 缺少支持窗口硬门禁 | Security GPT | Medium，加入 CI/RustSec/OSV gate |

## D-items（需用户裁决）

### D1: Command/API 事实源选择
**问题**: API/DX 双模型要求所有 Command、MCP、HostFunction、Error、limits 从单一 IDL/Schema 生成；现有文档分散定义。
**选项**: A. `game_api.idl` 成为唯一事实源，Markdown 只引用生成表；B. 保持 Markdown 为主，IDL 只做 SDK 参考。
**推荐**: A。理由：当前分叉已成为跨方向 Blocker，只有机器可读事实源能阻止 R16 继续出现 schema 漂移。

### D2: ECS 权威调度模型
**问题**: 文档同时追求 `.chain()` 简单确定性与 partial parallelism 性能收益。
**选项**: A. 固定 serial spine + manifest 声明 parallel sets；B. 全部 `.chain()`，牺牲并行换取简单确定性。
**推荐**: A。理由：Performance 已指出全 chain 难以达标；但 A 必须有 R/W manifest 与 CI 检查，否则不可证明。

### D3: WebSocket 后续消息安全等级
**问题**: 握手后免签是否允许承载 MCP mutation/debug/admin。
**选项**: A. WS 只做固定只读 subscription，mutation/admin 走 per-request signed REST/MCP；B. WS 可承载高价值消息，但必须 per-message seq/MAC/signature。
**推荐**: B for authenticated agent sessions, A for browser/public spectator。理由：保留实时体验，同时不牺牲 replay/audit/rate limit。

### D4: Economy 默认世界反雪球强度
**问题**: Vanilla 默认值应新手友好还是直接承担 Standard anti-snowball 目标。
**选项**: A. Tutorial/Novice 使用弱维护费，Standard 默认启用强超线性维护费；B. Vanilla 默认弱维护费，anti-snowball 作为可选 hard mode。
**推荐**: A。理由：文档当前承诺 Standard 世界有反雪球；若默认不启用，设计承诺与运行体验分叉。

### D5: Phase 2 完成后是否生成 R15.1 追加裁决
**问题**: Phase 2 已创建但不阻塞初步综合。
**选项**: A. 等 Phase 2 完成后追加 `R15-SPEAKER-VERDICT-ADDENDUM.md`；B. 直接把 Phase 2 结果作为 R16 输入。
**推荐**: A。理由：CrossCheck 已达到补漏阈值，追加裁决能保持 R15 可追溯闭环。

## 文档维护项
- 建议新增或生成 `docs/specs/reference/api-registry.generated.md`：CommandAction、MCP tool、HostFunction、Error taxonomy、limits 的单一展示面。
- 建议新增 `docs/specs/core/phase2b-system-manifest.md` 或把 manifest 提升为 01-tick-protocol 的唯一权威小节。
- 建议新增 `docs/specs/security/authz-matrix.generated.md`：所有 REST/MCP/WS 方法必须列入，未列方法启动失败。
- 建议新增 `docs/design/economy-balance-sheet.md`：Vanilla/Tutorial/Standard 的 1/5/20/50 房间数值表。
- 清理所有重复 budget 数字：commands/player/tick、output cap、COLLECT timeout、cgroup cpu.max、pids.max、CRL delay、path_find budget。
- 清理残留 Market/Contract/Merchant 入口，明确 MVP whitelist 与 RFC/Future 边界。

## 评审统计

| Direction | GPT-5.5 verdict | DeepSeek V4 Pro verdict | 主要信号 |
|-----------|-----------------|--------------------------|----------|
| Architect | REQUEST_MAJOR_CHANGES | REQUEST_MAJOR_CHANGES | 权威合同、ECS chain、Tick/FDB 语义冲突 |
| Security | REQUEST_MAJOR_CHANGES | CONDITIONAL_APPROVE | 授权矩阵、WS 免签、sandbox profile、CA/challenge |
| Designer | CONDITIONAL_APPROVE | CONDITIONAL_APPROVE | 设计方向可行，但首小时、策略学习、防守偏置需调优 |
| Performance | CONDITIONAL_APPROVE | CONDITIONAL_APPROVE | 容量预算不自洽，需 benchmark/admission contract |
| Economy | CONDITIONAL_APPROVE | CONDITIONAL_APPROVE | 反雪球参数、allied transfer、PvE budget 未闭合 |
| API/DX | REQUEST_MAJOR_CHANGES | REQUEST_MAJOR_CHANGES | schema/IDL/error taxonomy 不可生成 |
| Determinism | REQUEST_MAJOR_CHANGES | CONDITIONAL_APPROVE | 排序键、ECS 顺序、RNG/state machine 分叉 |

共识强度评估：
- Strong Blocker：B1/B2/B3/B4，均由至少 2 个方向与 2 个模型独立提出，且直接影响实现唯一性。
- Medium-Strong Blocker：B5/B6/B7，跨方向一致但部分问题可通过明确风险接受或容量降级解决。
- Positive Consensus：WASM-first、公平的 MCP 作为管理/学习界面、deferred command model、Blake3/IndexMap/定点整数方向、双层经济、World/Arena 分离均被多方向认可。
- 总体状态：设计核心理念仍被认可，但文档合同层未冻结；R15 应进入修订轮，而非实现启动。

## D-items 裁决结果

| D# | 裁决 | 说明 |
|----|------|------|
| D1 | **A** | `game_api.idl` 成为唯一事实源，Markdown 只引用生成表 |
| D2 | **A** | 固定 serial spine + manifest 声明 parallel sets（需 R/W manifest + CI 检查） |
| D3 | **B** | WS 承载高价值消息需 per-message seq/MAC/signature；browser/public spectator 走只读 subscription |
| D4 | **A** | Tutorial/Novice 弱维护费，Standard 默认强超线性维护费 |
| D5 | **A** | Phase 2 完成后追加 `R15-SPEAKER-VERDICT-ADDENDUM.md`，保持 R15 闭环 |
