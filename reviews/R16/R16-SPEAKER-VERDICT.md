# Swarm 设计评审 R16 — Speaker 共识报告

## 裁决概要

R16 是 R15 后 9 个 Blocker + 15 个 High 修复后的闭合验证轮。Phase 1 已完成 14/14 reviewers（7 方向 × 2 模型）。本轮总体结论：文档质量和设计成熟度继续提升，但“单一权威源”仍未真正闭合；新增的 api-registry、Phase 2b manifest、persistence contract、economy balance sheet 等文件在成为权威源的同时，与旧叙述/派生参考文档产生新的冲突。

收敛评估：R15 的若干具体问题已被修复（如 Direction4、SendMessage RFC 化、Resource Ledger、API registry 意识增强），但 R16 暴露出更高层的收敛问题：同一事实仍被多个文件手写定义，且这些文件均带有“权威”语义。该状态不适合 Freeze。

Freeze 状态：NOT FROZEN。

Phase 1 完成情况：14/14 reviewers。

Phase 2 补漏情况：根据 CrossCheck，已创建 7 个 Phase 2 补充任务（Architect / Security / Designer / Performance / Economy / API-DX / Determinism）。本裁决不等待 Phase 2；Phase 2 发现将作为追加项并入后续闭合。

## 总体 Verdict

REQUEST_MAJOR_CHANGES

理由：4/14 reviewers 给出 REQUEST_MAJOR_CHANGES，10/14 给出 CONDITIONAL_APPROVE，无 APPROVE。跨方向、跨模型共同指向的阻塞问题至少 6 组，且其中多组会导致实现分叉、replay 分叉、SDK/codegen 失败或经济数值不可验证。

## 共识 Blocker（跨方向 + 跨模型同意）

### B1: API Registry “单一权威源”未闭合，派生文档继续定义冲突 API/ABI/错误码

**方向 × 模型矩阵**:
- API/DX: rev-dsv4-apidx C1/C2/C3/C4/H1/H3/H4/H5；rev-gpt-apidx X1/X2/X3/X4
- Architect: rev-gpt-architect A1/A4；rev-dsv4-architect M5/L1-L3
- Determinism: rev-gpt-determinism T2/T7；rev-dsv4-determinism H3 cross-source consistency
- Designer: rev-gpt-designer G1；rev-dsv4-designer G5/G9/G10 相关 API/规则语义
- Security: rev-gpt-security H2；rev-dsv4-security C1/H2/H4 相关安全矩阵缺口
- Economy: rev-gpt-economy CrossCheck #1；rev-dsv4-economy D2

**问题**:
api-registry.md 声称是 CommandAction、RejectionReason、MCP Tools、Host Functions、容量限制的单一权威源，但 commands.md、02-command-validation.md、host-functions.md、interface.md、feedback-loop.md 等仍手写冲突事实：
- MCP 工具清单在 interface.md 与 api-registry.md 中大面积不重合。
- Host Function ABI 签名在 registry 与 host-functions/interface 中不同。
- RejectionReason 在 registry 与 validation/commands 中不闭合。
- CommandAction 数量、Spawn/SpawnDrone、Recycle 参数、Leech/Fabricate core/custom 边界冲突。
- IDL 被反复承诺为 codegen 源，但未定义格式、位置、schema、生成规则。
- API registry 缺少逐工具 authz/replay/visibility/subject_source 安全列，导致 codegen 可能生成 IDOR 风险接口。

**修正要求**:
1. 确定唯一机器事实源：要么 `game_api.idl` 为源、registry 为生成视图；要么 registry 本身机器可读化（YAML/JSON/IDL），Markdown 表格由它生成。
2. 删除或降级所有派生文档中的 enum、tool list、ABI signature、error code、limits 表。保留解释和示例，不再手写权威事实。
3. 使 CommandAction、CustomAction、RejectionReason、MCP tools、Host ABI、Limits、Error Envelope 全部闭合。
4. 为每个 MCP/REST/WS 方法补齐机器可读列：`required_scope`、`replay_class`、`subject_source`、`visibility_filter`、`rate_limit_key`、`admin_override`、`idempotency_key_required`、schema refs。
5. 添加 CI：扫描派生文档中的 Action/Reason/Tool/ABI 字面量，未注册或与源不一致即失败。

### B2: Phase 2a / Phase 2b / ECS System Manifest 存在互斥调度，直接导致状态转移分叉

**方向 × 模型矩阵**:
- Architect: rev-dsv4-architect C1/C2/C4/H3/H4/H5；rev-gpt-architect A3
- Determinism: rev-gpt-determinism T1/T6；rev-dsv4-determinism C1/H1
- Performance: rev-gpt-performance P1/P3；rev-dsv4-performance H3
- Designer/Economy: rev-dsv4-designer X1/G4；rev-gpt-economy CrossCheck #2

**问题**:
engine.md、01-tick-protocol.md、02-command-validation.md 与 06-phase2b-system-manifest.md 对 Phase 2a/2b 的边界和系统顺序给出不同实现：
- engine.md 描述 20-system flat `.chain()`；manifest 描述 27-system serial spine + parallel sets。
- spawn 与 death_mark 顺序冲突，决定 RoomCap 是否同 tick 释放给新 spawn。
- spawning_grace 在 manifest 中位于 combat/damage 之后，可能允许 birth-tick kill，违反 engine.md 的出生保护承诺。
- regeneration 在 combat 前还是后影响战斗平衡。
- command_executor/transfer/build/recycle 属于 Phase 2a inline 还是 Phase 2b manifest 不清。
- special attack parallel set 未表达 Disrupt/Fortify/Hack/Drain/Overload 的 deterministic reducer 顺序。

**修正要求**:
1. 将 06-phase2b-system-manifest.md 升级为唯一执行顺序源，或重命名/重构为完整 Tick Execution Manifest（同时覆盖 Phase 2a handlers 与 Phase 2b passive systems）。
2. 删除 engine.md / 01-tick-protocol.md 中可被实现者照抄的旧 `.chain()` 和旧顺序表，改为引用 manifest。
3. 明确 spawn/death_mark/RoomCap 生命周期、spawning_grace 添加与失效时机、regeneration/combat 顺序、pvp_block 位置。
4. 将 special attack 从“并行直接改状态”改为 pending intents -> canonical priority reducer -> status_advance 的确定性流程，或给出等价可验证的 R/W proof。
5. 补齐 Component/Resource R/W matrix，覆盖 manifest 中所有 27 systems 和 30+ components/resources。

### B3: Tick retry / persistence / replay 语义冲突，破坏 replay 闭包与故障恢复一致性

**方向 × 模型矩阵**:
- Architect: rev-gpt-architect A2；rev-dsv4-architect H1/M3
- Determinism: rev-gpt-determinism T4/T10；rev-dsv4-determinism L2
- Performance: rev-gpt-performance P2；rev-dsv4-performance H2
- Security: rev-gpt-security M3；rev-dsv4-security persistence cross-check

**问题**:
01-tick-protocol.md 与 05-persistence-contract.md 对 FDB commit 失败后的行为冲突：
- 01 要求 commit retry 复用同一 COLLECT 结果，不重跑 WASM，不追加 fuel，保持 TickTrace/commands/snapshot 稳定。
- 05 写“重新执行 tick N（重跑 COLLECT -> apply）”，甚至承认 TickTrace 可能因时间流逝不同。
这会同时破坏确定性、计费、公平、性能和 replay verification。

此外，对象存储先写再 FDB commit 的路径仍有 replay blob 损坏/不可读/被删除时的权威状态缺口；TickTrace WAL 本地路径的跨节点恢复语义也未闭合。

**修正要求**:
1. 统一为：commit retry 必须复用首次 COLLECT 的 canonical buffer（snapshot_hash、commands、wasm_status、fuel ledger），不得重跑 WASM。
2. TickTrace 增加或明确 `attempt_id`、`collect_id`、`commit_id`、retry_policy、object_blob_status。
3. 05-persistence-contract.md 删除“重跑 COLLECT”语义，改为“重新 apply cached collect result / 重新提交同一 canonical trace”。
4. 定义 object blob committed 后不可读/损坏的 terminal states：verified / audit_gap / unreplayable / reconstructable，并给恢复 runbook。
5. 将 FDB transaction size、object-store timeout、WAL fallback 纳入同一性能/确定性预算。

### B4: 性能容量合同与 target/hard cap 不匹配，worker pool、CPU、命令量、pathfinding 预算缺少 admission 策略

**方向 × 模型矩阵**:
- Performance: rev-dsv4-performance C1/H1/H2/H3；rev-gpt-performance P1/P2/P3/P4
- Architect: rev-dsv4-architect M1；rev-gpt-architect Missing #5/A7
- Security: rev-dsv4-security H2/H3；rev-gpt-security H4/M4
- Determinism: rev-dsv4-determinism H3；rev-gpt-determinism cache/SIMD/canonical concerns

**问题**:
文档声称单 Engine target 500 / hard cap 1000 active players，但资源合同缺少硬件基线和降级策略：
- worker pool = active_players 意味 500-1000 sandbox workers，按 128MB cgroup 上限可达 64-128GB sandbox 内存保留；CPU quota 推算 target 500 需要约 42+ cores，hard cap 1000 需要 84+ cores。
- COLLECT per-player 2500ms 依赖完全并行；一旦引入 max_pool 或 CPU 受限，固定 per-player deadline 会吞噬全局预算。
- Phase 2a 最坏 50k-100k commands/tick 串行 inline apply，对 400ms EXECUTE 预算无余量。
- pathfinding global 100k nodes 在 500/1000 玩家下仅 200/100 nodes/player/tick，可能让 `host_path_find` 高负载不可用。
- Tick budget 内部仍存在 400ms/500ms/no EXECUTE timeout、COLLECT 2500ms + 其他阶段 > 3000ms 的不一致。

**修正要求**:
1. 增加权威 Tick/Capacity Manifest，绑定 tick budgets、hardware baseline、active player caps、worker max_pool、CPU/memory admission、degraded mode。
2. 将 worker pool 从 `active_players` 改为 `min(max_pool, active_players)`，并定义排队、公平时间片、deadline 重新分配策略。
3. 区分 target/hard cap：target 是推荐硬件下 p99 SLA，hard cap 是 admission 上限且允许质量降级；两者不可共用同一性能承诺。
4. Phase 2a 增加 pre-admission/pre-aggregation、per-drone action collapse、rejection trace cap、100k command benchmark。
5. Pathfinding 改为 active_path_users/active_drones/rooms 加权 fair-share，并定义 negative cache/unreachable cap。
6. Metrics 必须区分 fuel exhausted、epoch timeout、cgroup throttled、host-call global budget exhausted、path budget exhausted。

### B5: 经济权威口径不统一，维护费、Recycle、存储税、Transfer 范围使平衡不可验证

**方向 × 模型矩阵**:
- Economy: rev-dsv4-economy D1/D2/D3；rev-gpt-economy E1/E2/E3/E5/E6/E7
- Designer: rev-dsv4-designer G3/G4/X4/X6；rev-gpt-designer G3/Product cross-check
- Architect/API: rev-gpt-architect A1；rev-dsv4-apidx C4/H2；rev-gpt-apidx X1

**问题**:
经济设计方向正确，但数值和权威公式不闭合：
- economy-balance-sheet 使用 `base_upkeep × rooms × (1 + rooms / room_soft_cap)`，gameplay 的 empire-upkeep mod 使用 `drones * drone_cost + rooms * (room_base + rooms * room_superlinear / FIXED_SCALE)`；两者参数体系不同且示例维护费相差数量级。
- balance sheet 中 1/5/20/50 房全部长期净亏，却声称“新手轻松/可承受/顶尖可维持”，缺少可行 break-even 场景。
- Recycle 在 gameplay/IDL 是固定 50%，Resource Ledger 是 lifespan 比例 10%-50%。
- storage tax 同时存在 tier、fixed 10bp、mode table 口径，缺少 equilibrium storage 与阶梯边界稳定性证明。
- AlliedTransfer、Drone P2P offer、messages、Market RFC 的当前范围冲突，可能打开绕过税/物流/小号输血限制的通道。

**修正要求**:
1. 指定 Resource Ledger + empire-upkeep mod 参数为经济实现权威，balance sheet 只验证该公式，不自创公式。
2. 重算 1/5/20/50 房收支，至少给出新手安全线、中期优化线、扩张上限线三个可复算场景。
3. 统一 Recycle 为一个方案。推荐以 Resource Ledger 的 lifespan depreciation 公式为权威，并让 IDL/gameplay 引用该公式。
4. 存储税统一使用 `global_storage_tax_tiers` 或明确 base/tier 叠加关系，补 equilibrium proof 和 worked examples。
5. 当前版本冻结为：只有 Resource Ledger Transfer/AlliedTransfer 可改变资源归属；messages 仅非执行 payload；Market/Drone P2P settlement 为 Future RFC 或明确非结算型 Challenge Board。

### B6: 安全权威矩阵未进入 API 源，WebSocket、Admin、nonce/CRL、sandbox OS 合同仍有冲突

**方向 × 模型矩阵**:
- Security: rev-gpt-security H1-H5；rev-dsv4-security C1/C2/H1-H4
- API/DX: rev-gpt-apidx CrossCheck Security；rev-dsv4-apidx MCP/auth schema gaps
- Architect/Performance/Determinism: sandbox/worker/transport/capacity cross-checks

**问题**:
安全设计基础扎实，但安全合同仍分散且冲突：
- auth.md 写 Agent WebSocket 握手后消息免签，MCP security 要求每条消息 `seq + body_hash + signature/MAC`。
- deploy nonce 机制在 auth.md §5.6a 与 §10.8 冲突（Dragonfly nonce vs FDB version_counter）。
- API registry 缺少 authz/replay/visibility/security matrix，且多工具 input 直接含 `player_id`，与 player_id 从证书主体派生的原则冲突。
- Admin source 有“无限制/可触发战斗”的表述，与 admin rate limit、cooldown、双签、审计要求冲突。
- Sandbox OS 隔离中 net namespace、clone/fork、pids.max 描述互斥。
- CVE/SLA 只覆盖 Wasmtime，未覆盖 rmcp/Bevy/wasmparser/crypto/auth/serialization/db clients。

**修正要求**:
1. Agent WS 统一为 per-message seq + body_hash + signature/MAC；browser spectator WS 明确只读隔离。
2. Deploy 防重放统一为 FDB version_counter；Dragonfly nonce 仅用于明确幂等且风险可接受路径。
3. API registry 合并逐工具安全矩阵，删除或标注所有 client-supplied `player_id` 为 forbidden/ignored，主体来自 authenticated principal/certificate。
4. Admin 拆分为 AdminRead/AdminConfig/AdminRollback/AdminSecurityAction 等 capability，全部有 rate limit、cooldown、idempotency、audit schema，Critical 双签。
5. Sandbox OS 生产基线唯一化：net namespace、clone/fork、pids.max、seccomp、cgroup 数值只在一个表定义。
6. 将 CVE-SLA 扩展为 Dependency Security SLA，按 Tier 0/1/2 覆盖关键 Rust crates 和基础设施客户端。

## CrossCheck 补漏发现（基于 Phase 2）

Phase 2 尚未完成；本裁决基于 Phase 1 14/14 报告立即启动综合。已创建补充任务，后续发现应作为 R16 addendum 或 R17 输入。

### CX1: Architect / API / Determinism 权威源交叉验证
**来源**: 多个 Phase 1 reviewer → 目标方向: Architect / API-DX / Determinism
**发现**: API registry、system manifest、persistence contract 均自称权威，但派生文档仍有可执行冲突。
**处置**: 升级为 Blocker（B1/B2/B3）。

### CX2: Security matrix 与 API registry 合并
**来源**: rev-gpt-security、rev-gpt-apidx、rev-dsv4-security → 目标方向: Security / API-DX
**发现**: registry 缺失 required_scope、subject_source、visibility_filter、replay_class 等安全列。
**处置**: 升级为 Blocker（B1/B6）。

### CX3: Performance / Infra 容量基线
**来源**: rev-gpt-performance、rev-dsv4-performance、rev-dsv4-architect、rev-dsv4-security → 目标方向: Performance / Architect
**发现**: target/hard cap 未绑定硬件、worker pool、CPU quota、admission 策略。
**处置**: 升级为 Blocker（B4）。

### CX4: Economy / Designer 数值与产品动机
**来源**: rev-gpt-economy、rev-dsv4-economy、rev-dsv4-designer、rev-gpt-designer → 目标方向: Economy / Designer
**发现**: balance sheet、storage tax、Recycle、World motivation、Arena↔World bridge 需要联合裁定。
**处置**: 经济公式类升级为 Blocker（B5）；产品动机类记录为 High（D-H1/D-H2）。

## 方向专属 High 优先级

### A-H1: Engine/Manifest 权威边界与历史代码块清理
Architect 方向需在所有架构文档开头增加 Authority / Non-authority 块，明确本文件定义什么、不定义什么、冲突时以谁为准。尤其 engine.md 中旧 `.chain()`、旧 Phase 表和 manifest 必须不再并存为可实现参考。

### S-H1: Agent WS、API subject_source、Admin capability、Sandbox OS 单表化
Security 方向需将 transport/authz/replay/admin/sandbox 的安全不变量纳入机器可读源，避免安全文档与 API/codegen 分裂。

### D-H1: World 模式动机真空与长期目标不足
Designer 方向需要为 World 模式补最小进展/身份/声誉/创作性目标。rev-dsv4-designer 将其列为 Critical；rev-gpt-designer 也指出首小时情绪峰值、Replay 传播和长期身份目标不足。

### D-H2: Replay / Spectator / Highlight 产品闭环
Replay safe URL、minimal highlight/first victory card、public replay privacy、spectator_view_mode 至少应作为 MVP-adjacent 合同，而非完全 Future RFC；否则社区传播力不足且安全边界不明。

### P-H1: Worker pool 和 tick budget admission
Performance 方向需给出硬件基线、max_pool、dynamic per-player deadline、command admission、host-call/path-call 全局预算。否则 target/hard cap 是愿景不是合同。

### E-H1: Economy balance sheet 必须验证实现公式，而非独立公式
Economy 方向需统一 balance sheet 与 empire-upkeep mod，并用同一 Resource Ledger/IDL 参数重算所有示例。

### X-H1: IDL / schema / MCP tools codegen 本体缺失
API/DX 方向需定义 `game_api.idl` 的格式、位置、schema refs、生成路径、版本策略。46 个 MCP tools 不能只靠 Markdown 参数简写。

### T-H1: Determinism draw-level RNG / canonical codec / SIMD policy
Determinism 方向需定义 event-keyed counter-based RNG、canonical codec/hash、World SIMD 默认策略和 TickTrace replay 边界。dsv4-determinism 将 World SIMD 默认 true 列为 Critical；gpt-determinism 将其列为 Low/strategy gap，但二者都要求明确跨架构边界。

## Medium/Low 处置

| ID | 问题 | 来源方向 | 处置 |
|----|------|---------|------|
| M1 | Snapshot truncation 两套 priority model / distance_to_drone 未指定代表 drone | Architect / Determinism | 并入 Determinism cleanup；不单独 Blocker，但必须在 manifest/codegen 前修复 |
| M2 | JSON canonicalization / command_hash 使用 raw JSON | Architect / Determinism / API-DX | 并入 B1/T-H1；建议采用 canonical binary IDL 或 RFC8785/JCS |
| M3 | public_spectate 与 player_view/spectator_delay 交互不明 | Designer / Security | Medium；增加 `spectator_view_mode` 并默认 player_perspective 或 delayed_full |
| M4 | PvE faucet budget 与 Source/event/drop/Blueprint 统一预算缺失 | Economy | Medium；补 classification 表和 budget inclusion 规则 |
| M5 | Controller age repair formula controller_count 项歧义 | Economy / Designer | Medium；需用户或设计 owner 裁定公式语义 |
| M6 | World leaderboard / showcase 命名冲突 | Designer | Medium；World 改为 showcase/chronicle/stats，Arena 才用 leaderboard |
| M7 | Object store ACL/immutability/delete threat model | Security | Medium；补对象存储安全基线和恢复 runbook |
| M8 | Dependency EOL / Wasmtime `=30.0` 迁移计划 | Security / Determinism | Medium；纳入 Dependency Security SLA |
| M9 | First-hour content pacing / onboarding smoke test | Designer / API-DX | Medium；补验收路径和 AI 按 MCP docs 完成 basic-agent 部署测试 |
| M10 | Drone messaging DoS / recipient cap | Designer / Security | Medium；补每 drone 接收 cap、snapshot budget 分类、constant-time processing |
| L1 | api_version semver string vs u32 | API/DX | Low；拆 `api_semver` 与 `schema_revision` |
| L2 | resources/list slash 命名 | API/DX | Low；明确是 MCP resource endpoint 还是 tool |
| L3 | curiosity idle movement 破坏 cosmetic-only | Designer | Low；改为纯动画或明确 gameplay mechanic |
| L4 | Fabricate Matter 与 Vanilla Energy-only 冲突 | Designer | Low；Fabricate 改 opt-in 或改 Energy-only 默认 |
| L5 | code_update_cost 示例 Energy/Crystal 不一致 | Designer | Low；统一示例或加资源前提说明 |

## D-items（需用户裁决）

### D1: ECS 执行权威是完整 Tick Execution Manifest，还是保留 Phase 2a inline + Phase 2b manifest 双层？

**问题**: 当前 engine.md、tick protocol、command validation、phase2b manifest 同时定义执行顺序。

**选项**:
- A. 建立完整 Tick Execution Manifest：Phase 2a command handlers + Phase 2b passive systems 全部在一个机器可读 manifest 中定义。
- B. 保留 Phase 2a inline apply 为 engine.md 权威，Phase 2b manifest 仅定义 passive systems。

**推荐**: A。理由：当前分叉的根因就是 Phase 2a/2b 双权威。完整 manifest 可同时驱动实现、CI、R/W proof、TickTrace `system_manifest_hash`。

### D2: Recycle 退还规则采用固定 50%，还是 lifespan depreciation 10%-50%？

**问题**: gameplay/IDL 与 Resource Ledger 冲突。

**选项**:
- A. 固定 50% body cost refund。
- B. Resource Ledger 方案：remaining_lifespan 比例，10%-50%。

**推荐**: B。理由：更有策略深度，减少临死前固定 50% 的低成本重构/回收套利，并已有 Ledger 公式。

### D3: World 模式是否默认启用 WASM SIMD？

**问题**: dsv4-determinism 认为 World 默认 SIMD true 是 Critical 确定性缺口；performance 认为是性能/确定性 tradeoff。

**选项**:
- A. World/Arena 默认均 `simd_enabled=false`；服务器可显式开启并记录 CPU feature fingerprint。
- B. World 默认 true，但 TickInputEnvelope 记录 `simd_arch_fingerprint`，跨架构 replay/迁移需匹配。

**推荐**: A。理由：Freeze 前优先确定性和可复现，性能优化可作为显式 opt-in。

### D4: World 模式是否允许“非竞争展示榜”？

**问题**: World 无 leaderboard 与 `swarm_get_leaderboard {gcl, rooms, drones}` 冲突。

**选项**:
- A. World 不使用 leaderboard 术语，仅有 showcase/chronicle/world_stats。
- B. 保留非竞争展示榜，但显式标注非胜负排名。

**推荐**: A。理由：避免玩家把不公平持久世界理解为竞技排行；Arena 才承载 leaderboard/season/rating。

### D5: Replay sharing / highlight card 属于 MVP-adjacent 还是 Future RFC？

**问题**: Designer 认为传播闭环若完全推迟，会削弱核心增长；Security 要求隐私边界明确。

**选项**:
- A. MVP-adjacent：至少 safe share URL + minimal highlight/first victory card。
- B. Future RFC：MVP 只提供 raw replay viewer。

**推荐**: A。理由：不要求复杂社区系统，但 safe share 与最小战报卡是产品学习/传播闭环的一部分，并可同时定义隐私边界。

## 文档维护项

1. 建立 `api-registry.yaml` / `game_api.idl` / `system-manifest.yaml` / `limits.yaml` 等机器可读源；Markdown 表格由生成器输出。
2. 每个核心文档增加 `Authority / Non-authority` 块。
3. 删除或标注所有旧表格、旧代码块、旧 enum、旧 tool names、旧 host ABI signatures。
4. 增加 cross-doc CI：Action/Reason/Tool/ABI/Limit/ReplayClass/AuthScope/VisibilityFilter/ManifestHash 一致性。
5. 增加性能 benchmark gates：500/1000 active players 推演、50k/100k commands、pathfinding fair-share、worker pool max_pool、FDB transaction size、object-store timeout。
6. 增加经济验证表：维护费公式、storage tax equilibrium、1/5/20/50 房 break-even、Recycle strategy analysis、PvE faucet classification。
7. 增加安全 Dependency SLA：Wasmtime 之外覆盖 rmcp、Bevy、wasmparser、auth/crypto、serde/compression、db clients。
8. 文档索引需标记 R16 verdict 与 Phase 2 addendum；若 Phase 2 输出新增 blocker，应在 R16 addendum 或 R17 入场条件中引用。

## 评审统计

### 7×2 verdict/severity 矩阵

| Direction | GPT-5.5 | DeepSeek V4 Pro | 共识强度 |
|---|---|---|---|
| Architect | CONDITIONAL_APPROVE；High: authority/retry/manifest | REQUEST_MAJOR_CHANGES；Critical: ECS schedule/spawning grace/RW matrix | 强：两模型均认为执行顺序/权威边界需修复 |
| Security | REQUEST_MAJOR_CHANGES；High: WS/authz/admin/sandbox/SLA | CONDITIONAL_APPROVE；Critical: deploy nonce conflict/CRL window | 中强：安全架构可行，但合同冲突必须收敛 |
| Designer | CONDITIONAL_APPROVE；High: MCP naming/first-hour | CONDITIONAL_APPROVE；Critical: World motivation；High: Arena bridge/tax/defense | 中：设计可玩，但产品动机与传播边界需补强 |
| Performance | CONDITIONAL_APPROVE；High: tick budget/CPU/commands/path | CONDITIONAL_APPROVE；Critical: worker pool cliff；High: deadlines/FDB/Phase2a | 强：容量合同不足是明确共识 |
| Economy | CONDITIONAL_APPROVE；High: upkeep/balance/transfer | CONDITIONAL_APPROVE；Critical: balance-sheet vs mod formula；High: Recycle/storage tax | 强：经济公式与数值闭环未冻结 |
| API/DX | CONDITIONAL_APPROVE；High: registry/host ABI | REQUEST_MAJOR_CHANGES；Critical: MCP tool divergence/Host ABI/RejectionReason/object_id | 极强：API/codegen 单源未闭合 |
| Determinism | REQUEST_MAJOR_CHANGES；Critical: Phase2b schedule/registry closure | CONDITIONAL_APPROVE；Critical: schedule conflict/SIMD | 极强：确定性主轴正确，但权威执行合同未闭合 |

### Verdict 计数

- APPROVE: 0/14
- CONDITIONAL_APPROVE: 10/14
- REQUEST_MAJOR_CHANGES: 4/14
- REJECT: 0/14

### 共识强度评估

- 极强共识 Blocker：B1 API/registry/codegen、B2 ECS/manifest schedule、B3 retry/persistence、B4 capacity/performance。
- 强共识 Blocker：B5 economy formula/balance closure。
- 中强共识 Blocker：B6 security matrix/transport/admin/sandbox conflicts。
- 方向内强但跨方向较弱的 High：World motivation、Replay highlight、defensive balance、spectator UX。

## D-items 裁决结果

| D# | 裁决 | 说明 |
|----|------|------|
| D1 | **A** | 完整 Tick Execution Manifest（Phase 2a handlers + 2b systems 统一） |
| D2 | **B** | Recycle lifespan 比例 10%-50%（Resource Ledger 公式为权威） |
| D3 | **B** | World 默认 SIMD true，TickInputEnvelope 记录 `simd_arch_fingerprint` |
| D4 | **A** | World 仅 showcase/chronicle/world_stats，Arena 用 leaderboard |
| D5 | **A** | MVP-adjacent：safe share URL + minimal highlight/first victory card |

## R17 入场条件

R17 不应在当前文档状态下直接启动。建议先完成以下修复并提交：
1. B1-B6 全部闭合，至少形成机器可读权威源与删除派生冲突表。
2. D1-D5 由用户或 design owner 裁决并落文档。
3. Phase 2 补充任务返回后，若有新增 Blocker，合并进修复清单。
4. 修复后再进行 R17 14-reviewer clean-slate 验证，重点不再检查 R15 历史项，而检查权威源是否真正单一、生成物是否一致。
