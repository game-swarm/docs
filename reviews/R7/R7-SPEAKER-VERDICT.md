# Swarm 设计评审 — Speaker 共识报告

## 裁决概要

R7 是 clean-slate 全量设计评审。本轮 9/9 评审官均有可追溯输出，其中 6 份为文件产物，3 份为 Kanban handoff/comment 产物；缺失集中输出的 Claude/DeepSeek 报告已通过 retry 任务、父任务 metadata 与 comment thread 纳入统计。

总体收敛状态：设计方向已成熟，MCP 非 gameplay 通道、WASM-only gameplay、公平 fuel、visibility oracle、TickTrace/replay、Rhai trust chain 等核心方向获得广泛认可；但实现冻结仍不成立。主要原因是 Architect 与 Designer 两个方向均出现多数 REQUEST_MAJOR_CHANGES，且若干问题横跨架构、玩法与安全合同：ECS 主链不一致、Leech/Fabricate 官方能力合同缺失、RuleMod/Rhai capability 边界分叉、Gateway/MCP transport auth 降级、WASM sandbox 硬边界冲突。

Freeze 状态：**NOT FROZEN**。进入实现前必须先做一次 R7 blocker cleanup，并重新跑至少聚焦复审；若目标是 Phase 0 freeze，应继续完整 9/9 clean-slate 复审。

## 总体 Verdict

**REQUEST_MAJOR_CHANGES**

理由：9 名评审官中 4 名给出 REQUEST_MAJOR_CHANGES，5 名给出 CONDITIONAL_APPROVE。按方向统计：Architect 2/3 请求重大修改，Designer 2/3 请求重大修改，Security 3/3 条件通过但均存在 High 项。跨方向看，至少 4 类问题同时被 ≥2 个方向、≥2 个模型触及，满足 Speaker 升级为共识 Blocker 的条件。

## 共识 Blocker (跨方向 + 跨模型同意)

### B1: Leech/Fabricate 作为官方特殊攻击的合同未闭合

**方向 × 模型矩阵**:
- Designer: rev-claude-designer, rev-gpt-designer, rev-dsv4-designer
- Architect: rev-gpt-architect (CommandIntent/IDL/schema drift), rev-claude-architect (spawn/body_cost 与 lifecycle 相关一致性风险)
- Security: rev-gpt-security (Rhai/RuleMod capability drift adjacent), rev-claude-security (refund/session deploy-reset adjacent)

**问题**: 文档把 8 种特殊攻击写成 Vanilla Standard+ 官方能力，但 core validation 与 IDL 对 Leech/Fabricate 没有与 Hack/Drain/Overload/Debilitate/Disrupt/Fortify 同等级的命令定义、目标校验、失败语义、资源/建筑转换、反制窗口与 TickTrace 记录。Designer 三方均指出该问题；GPT Designer 与 DeepSeek Designer 明确指出 Fabricate 可绕过建筑成本/RCL/领土/结构类型约束，Claude Designer 指出 Standard tier 与 Tier gate/custom action 能力矛盾。

**修正要求**:
1. 选择唯一方案：A) Tier 1/Vanilla Standard 只包含 6 种特殊攻击，Leech/Fabricate 延后到 Tier 2/custom actions；或 B) 将 Leech/Fabricate 提升为核心 IDL/validation/reference 的一等命令。
2. 若选择 B，补齐 `specs/core/02-command-validation.md` 与 `specs/gameplay/08-api-idl.md` 的完整章节：字段 schema、body part 绑定、cooldown、visibility/range、target state、failure/refund、TickTrace、replay 语义。
3. Fabricate 必须定义 `structure_type` 或固定映射、建筑白名单、build_cost/RCL/max_per_room/terrain/territory 校验、neutral/spawning/grace 禁止规则，以及是否需要 channel/counterplay。
4. Leech 必须定义 cooldown、damage/heal ordering、可被 Disrupt/Fortify/visibility 反制的边界，避免 sustain dominant strategy。

### B2: ECS / Tick 主链与命令管线的唯一权威来源未闭合

**方向 × 模型矩阵**:
- Architect: rev-claude-architect, rev-gpt-architect, rev-dsv4-architect
- Security: rev-gpt-security (WASM output / validation drift), rev-dsv4-security (path_find quota drift), rev-claude-security (refund/deploy reset drift)
- Designer: rev-gpt-designer (Overload reference drift), rev-dsv4-designer (IDL/Standard tier drift)

**问题**: Architect 组核心共识是实现合同仍存在多处“哪个文档说了算”的风险。Claude Architect 将 Phase 2b ECS 主链跨 5 文档 4 版本不一致评为 Critical；GPT Architect 指出 mutating pipeline 与 Source Model/MCP 非 gameplay 合同冲突、CommandIntent schema/IDL/reference 漂移；DeepSeek Architect 指出 `omitted_count`、截断距离、Controller repair 语义漂移。Security 与 Designer 方向也在各自领域发现相同模式：Gateway vs MCP auth、sandbox profile、Overload reference、Leech/Fabricate IDL。

**修正要求**:
1. 明确 `specs/core/01-tick-protocol.md` 的 ECS 主链为唯一权威来源，并同步 `design/engine.md`、`design/gameplay.md`、`specs/core/07-world-rules.md` 中所有代码块/散文示例。
2. 将入口拆成 `GameplayMutationPipeline` 与 `ManagementPipeline`：只有 `WASM` 及明确特权来源可进入 gameplay mutation；MCP query/deploy、普通 REST、docs/schema 等不得进入。
3. 将 `specs/gameplay/08-api-idl.md` 设为 CommandAction schema 单一真相，删除/改写旧 envelope 示例，统一 `seq/sequence`、`action.type`、`target_id/controller_id`、`MAX_COMMANDS_PER_PLAYER/maxItems`。
4. 为跨文档引用加入维护规则：reference 示例必须由 IDL/schema 生成或被 CI 校验，不再手写漂移。

### B3: Security boundary canonical tables 不唯一，导致实现可按宽松解释落地

**方向 × 模型矩阵**:
- Security: rev-gpt-security, rev-claude-security, rev-dsv4-security
- Architect: rev-gpt-architect (sandbox hard values), rev-dsv4-architect (oracle truncation), rev-claude-architect (spawn refund fuel/resource confusion)

**问题**: 三名 Security 评审均给出 CONDITIONAL_APPROVE，但 High 项都指向同一类问题：安全边界表不唯一。GPT Security 指出 Gateway/MCP transport auth 在 Gateway 协议中丢失 mTLS/signed request 强制要求、WASM sandbox OS 边界在同文档内冲突、Rhai RuleMod capability 边界冲突、超大 WASM 输出语义冲突。Claude Security 指出 WS JWT query string 泄露、refund credit reconnect+same-session 部署例外绕过 deploy reset。DeepSeek Security 指出 Rhai `allowed_flags` 白名单未定义、`host_path_find` determinism failure 返回协议缺失。

**修正要求**:
1. 建立唯一 `Transport Auth Matrix`：browser WS、REST、MCP/Agent、replay/admin 各自的 JWT `aud`、`X-Swarm-Transport`、mTLS/signed request、Origin/CSRF、失败码与审计字段必须同表定义，并由 `specs/security/03` 与 `specs/12` 共同引用。
2. 建立唯一 `Sandbox Profile`：syscall allow/deny、clone policy、namespace、cgroup cpu/pids/memory、I/O、CI acceptance tests 只保留一组数值。
3. 建立唯一 `RuleMod Capability Matrix`：默认 world-level 能力与可选 player/entity-level 能力分离；若允许玩家/实体级修改，必须通过 `mod.toml/world.toml` 显式 grant、rate limit、target kind、audit/rollback。
4. 明确 `host_path_find` quota exceeded 返回码、WASM output 超限是整批拒绝还是截断、refund credit 在 deploy/reconnect/same-session 下的清零或衰减规则。

### B4: Tier 1 容量、性能预算与生命周期经济模型仍存在不可实现/可利用边界

**方向 × 模型矩阵**:
- Architect: rev-claude-architect, rev-gpt-architect
- Designer: rev-dsv4-designer, rev-claude-designer
- Security: rev-dsv4-security (fork pressure), rev-claude-security (refund credit)

**问题**: Claude Architect 指出 500 active players、≤500 total drone、`max_drones_per_player=500` 互相不可调和；GPT Architect 指出 500 players × per-player 2500ms COLLECT 没有 executor pool/capacity model；DeepSeek Security 将 per-player per-tick fork pressure 列为 Low，但与架构容量问题叠加后成为实现前必须澄清的边界。Designer 方向还指出 room count / territorial snowball 缺少 empire upkeep 或扩张成本，以及 Recycle/TOUGH/ATTACK lifecycle 数值可能形成 dominant strategy。

**修正要求**:
1. 明确 Tier 1 容量公式：active players、average drones/player、total drones、rooms、snapshot size、tick interval、worker pool size 的一致目标。
2. 补 `WasmExecutorPool` 合同：worker 并发数、排队 deadline、未调度玩家语义、compiled module cache 与 per-tick store/instance/process lifecycle 的安全边界。
3. 选择 50 players × 10 drones、500 players × 10 drones、或其他明确 MVP 容量；同步 `max_drones_per_player` 与 Tier gate。
4. 对 territorial snowball 增加至少一种可配置约束：empire upkeep、progressive claim cost、distance admin overhead，或明确 World mode 不提供竞争榜单且此项 Phase 1+ deferred。

## 方向专属 High 优先级

### A-H1: `omitted_count` / snapshot truncation / multi-room distance 确定性合同

来源：rev-dsv4-architect F1/F2，rev-gpt-security output JSON/snapshot_len，rev-dsv4-security M1/M2。

处置：将 `omitted_count` 与 `snapshot_len` 泄露风险在 core/security 中统一；多房间截断距离定义为同房间最近 drone，否则 ∞；所有 truncation 排序必须 replay deterministic。

### A-H2: Controller repair / aging_system / lifecycle 主链语义

来源：rev-claude-architect A4，rev-dsv4-architect F3，rev-claude-designer active_aging/TOUGH-ATTACK concerns。

处置：补 `aging_system` 在 ECS 主链的位置；统一 Controller repair 是 per-drone 还是 global total；为 body part `age_modifier` 增加总 cap 或解释 65x lifespan gap 的设计意图。

### S-H1: Gateway WS/JWT 与 MCP auth 泄露/降级

来源：rev-claude-security H1，rev-gpt-security High transport auth。

处置：禁止 browser WS token 放 query string；若保留，必须 nginx log redaction + Referer policy + short-lived one-time token。MCP production endpoint 必须 `JWT aud=mcp:*` AND (mTLS OR Ed25519 signed request)。

### S-H2: Rhai `allowed_flags` 与 capability grant

来源：rev-dsv4-security H1，rev-gpt-security High RuleMod capability，rev-claude-security M6。

处置：定义 `allowed_flags` 默认列表、deny/audit 行为、capability grant schema、per-tick quota 与 immune_* 子命名空间。

### D-H1: Overload reference 仍保留全图 fuel-oracle 语义

来源：rev-gpt-designer G1，rev-claude-designer Overload/cooldown，rev-dsv4-designer H1。

处置：以 validation + visibility spec 为准更新 `specs/reference/commands.md`：删除全图/无 range/fuel floor 可区分语义；明确 visible target、range、target cooldown、equivalent rejection classes、floor no-op 等价返回。

### D-H2: First-hour / AI onboarding / Replay 社区传播是 Phase 1+ 产品风险

来源：rev-gpt-designer G4/G5/G6，rev-claude-designer tutorial/PvE concerns，rev-dsv4-designer Market Contracts spec gap。

处置：不阻塞核心实现，但需进入 Phase 1 backlog：MCP resource manifest、starter bot artifact、ReplayShareCard/MatchSummary、market contracts 明确 MVP 或 future。

## Medium/Low 处置

| ID | 问题 | 负责 Phase | 处置 |
|---|---|---:|---|
| M1 | Spectator delay World/Arena 默认冲突 | Phase 0 cleanup | World public_spectate 默认 false；开启时 delay ≥50；Arena 可单独实时但 UI 标记 |
| M2 | `host_path_find` explored_nodes quota / return code drift | Phase 0 cleanup | core/02 与 core/04 同步；定义 `PATHFIND_QUOTA_EXCEEDED=-3` |
| M3 | `swarm_get_schema` / `swarm_get_world_rules` 限流不一致 | Phase 1 | 加 schema 低频限流或声明静态 schema 不限流 |
| M4 | Tick drift accumulation policy 未定义 | Phase 1 | 增 `tick_drift_policy=compensate`，Arena 强制 |
| M5 | Recycle combat refund / lifecycle dominant strategy | Phase 1 balance | 对 recently-damaged drones 降 refund 或要求 Spawn range |
| M6 | Market Contracts 出现在首小时机制但无 spec | Phase 1/Future 裁决 | 写 MVP contract 或从 MVP checklist 移除 |
| M7 | Replay share artifact/schema 缺失 | Phase 1 product | 定义 `ReplayShareCard` / `MatchSummary` |
| M8 | MCP AI-only onboarding manifest 缺失 | Phase 1 product | 定义 `swarm://manifest`、starter bot、ABI/version、acceptance test |
| L1 | soft_launch PvP 1 tick race | Phase 1 polish | 增 `soft_launch_grace_tick=1` |
| L2 | fork pressure 未量化 | Phase 1 perf | benchmark + worker pool doc |
| L3 | PvE event deterministic farming | Phase 2 | 可验证但不可提前预测的 epoch seed reveal |

## 文档维护项

1. 将 R7 所有报告归档到 `/data/swarm/docs/reviews/R7/`，避免部分报告散落在 Kanban workspace/comment 中。建议补建：
   - `/data/swarm/docs/reviews/R7/rev-dsv4-architect.md`
   - `/data/swarm/docs/reviews/R7/rev-dsv4-security.md`
   - `/data/swarm/docs/reviews/R7/rev-dsv4-designer.md`
   - `/data/swarm/docs/reviews/R7/rev-claude-security.md`
2. 更新 `/data/swarm/docs/reviews/README.md`：记录 R7 verdict、9/9 完成状态、Speaker 输出路径。
3. 对 `specs/reference/` 明确“非主要评审目标但会影响实现者”的地位：如果 reference 仍存在，应纳入 schema/IDL CI 校验，不能与 core spec 漂移。
4. 清理 “从 kanban 日志提取 / write_file bug” 临时说明，或保留为审计注记但补齐正式报告文件。

## 评审统计

### 3×3 Verdict 矩阵

| Direction | Claude Opus 4.7 | GPT-5.5 | DeepSeek V4 Pro |
|---|---|---|---|
| Architect | REQUEST_MAJOR_CHANGES | REQUEST_MAJOR_CHANGES | CONDITIONAL_APPROVE |
| Security | CONDITIONAL_APPROVE | CONDITIONAL_APPROVE | CONDITIONAL_APPROVE |
| Designer | REQUEST_MAJOR_CHANGES | REQUEST_MAJOR_CHANGES | CONDITIONAL_APPROVE |

### Severity 概览

| Direction | Critical | High | Medium/Low | 主导风险 |
|---|---:|---:|---:|---|
| Architect | 1+ | 8+ | 10+ | ECS/IDL/容量/预算合同不闭合 |
| Security | 0 | 8 | 14+ | transport/sandbox/Rhai/refund 边界不唯一 |
| Designer | 1+ | 8+ | 12+ | Special attacks/Overload/Fabricate/长期目标 |

### 共识强度评估

- **强共识 Blocker**: B1 Leech/Fabricate，B2 ECS/IDL/pipeline authority，B3 security canonical boundary tables。
- **中强共识 Blocker**: B4 Tier 1 capacity/performance/economy boundary。
- **方向内强一致**: Security 全员认为方向正确但需修 High；Designer 全员指向 special attack 合同缺口；Architect 全员指向实现合同漂移。
- **未解决分歧**: 是否将 Leech/Fabricate 保留为 Tier 1 官方能力，还是降级到 Tier 2/custom actions；是否用 500 active players 还是 500 total drones 作为 Tier 1 主容量目标；World mode 是否需要 empire upkeep 作为硬合同。以上三项需用户裁决或设计 owner 选择。

## R8 入场条件

1. 先完成 B1-B4 的文档 cleanup，且每个 blocker 有明确 diff 与唯一权威表。
2. 对三个需用户裁决项给出选择并同步所有相关文档。
3. 重新启动完整 9/9 clean-slate review，或至少先跑 Architect+Designer+Security 各 3 人的 blocker closure review。
4. Speaker 下一轮不应基于本轮修正前报告宣布 freeze；修正后报告必须重新生成。
