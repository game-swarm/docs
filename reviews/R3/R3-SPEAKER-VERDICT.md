# Swarm R3 设计评审 — Speaker 共识报告

> Speaker: rev-speaker  
> Round: R3  
> 输入: 9/9 评审员已完成（Architect ×3, Security ×3, Designer ×3）  
> 输出日期: 2026-06-16

---

## 裁决概要

R3 评审完成度为 9/9，无缺席。总体收敛信号是：所有方向都认可 Swarm 的核心路线已经正确——AI 与人类同走 WASM、MCP 不是 gameplay executor、Source Gate + validate_and_apply 单入口、is_visible_to 单一可见性函数、deterministic tick/replay 合同是正确主干。

但本轮不是 Freeze。Security 方向 3/3 均给出 REQUEST_MAJOR_CHANGES；Architect 方向出现 1 个 REQUEST_MAJOR_CHANGES、1 个 APPROVE_WITH_RESERVATIONS、1 个 APPROVE；Designer 方向 3/3 为 APPROVE_WITH_RESERVATIONS。跨方向聚合后，多个问题同时被 Architect 与 Security 标记，并且至少 2 个模型独立发现，达到共识 Blocker 门槛。

Freeze 状态: NOT FROZEN。进入实现前必须先关闭下列共识 Blocker；Gameplay 方向的数值/体验项可分为“编码前必须补齐的规则边界”和“P1+ 产品化/内容项”。

## 总体 Verdict

REQUEST_MAJOR_CHANGES

理由：本轮没有发现“项目方向错误”或“必须重做”的根本性问题，因此不是 REJECT；但 Security/Architecture 层存在多项上线前不可接受的不一致、旁路和资源等价问题，不能仅以 Reservations 通过。

---

## 方向内交叉评审摘要

### Architect 组

评审员: rev-claude-architect, rev-gpt-architect, rev-dsv4-architect

3/3 赞同点:
- 核心架构主线正确：AI==Human WASM 执行路径、MCP 不做 gameplay action、determinism/replay/FDB 原子提交是正确方向。
- Phase 2a inline apply + Phase 2b ECS 的二段 tick 模型总体合理。
- 文档仍有实现前需澄清的读源/调度/一致性边界。

2/3 多数点:
- Rhai process isolation 与 in-process Bevy 示例存在架构冲突（rev-gpt-architect, Security 方向强烈支持；rev-claude-architect以能力白名单/爆炸半径形式提出）。
- host_path_find / host function 成本模型不是资源等价（rev-gpt-architect + rev-dsv4-security）。
- FDB/Bevy 双权威、rollback、tick boundary read source 需要更硬的失败矩阵（rev-claude-architect, rev-gpt-architect；rev-dsv4-architect降为低优先级澄清）。

1/3 孤点或低共识点:
- rev-gpt-architect 独立强调 Dynamic CommandAction 与强类型 IDL/SDK 的边界悖论。
- rev-claude-architect 独立强调 security_epoch bump 后全量重编译容量/runbook。
- rev-dsv4-architect 给出 APPROVE，认为 Bevy 自动调度能处理 RW 冲突；该观点被记录为 severity 分歧，但未推翻多数风险。

### Security 组

评审员: rev-claude-security, rev-gpt-security, rev-dsv4-security

3/3 赞同点:
- 当前安全合同仍需重大修改，Security 方向 3/3 verdict = REQUEST_MAJOR_CHANGES。
- Rhai/mod 安全模型、隔离模型或信任链存在上线前必须收敛的风险。
- WASM/deploy/compile/cache/epoch 相关安全合同不够硬，不能依赖人工审查或含糊缓存键。
- MCP/可见性/模拟/拒绝路径等“只读或失败输出面”仍可成为信息泄露通道。

2/3 多数点:
- Overload 静默 no-op 仍存在 side-channel 或竞争窗口（rev-dsv4-security, rev-gpt-security；Designer/Architect也从公平性与复杂度角度支持）。
- deploy_nonce / session / compile TTL 状态机需要 audience-bound、atomic consume、明确生命周期（rev-claude-security, rev-gpt-security, rev-dsv4-security 的表述不同但指向同一控制面状态机）。
- Snapshot truncation / simulate / replay 输出边界可能造成泄露或 DoS（rev-claude-security, rev-gpt-security, rev-dsv4-security）。

1/3 孤点或低共识点:
- rev-claude-security 独立提出模组 trust key 撤销/过期/吊销路径作为 Critical。
- rev-gpt-security 独立提出 Wasmtime =30.0 与 2026 advisory reality 不匹配作为 Critical。
- rev-dsv4-security 独立强调 refund credit 跨部署 session 语义和 Overload 多方合谋探测。

### Designer 组

评审员: rev-claude-designer, rev-gpt-designer, rev-dsv4-designer

3/3 赞同点:
- 游戏核心幻想强：“你的代码就是你的军队”，WASM-only gameplay path 是品牌与公平性的核心。
- World Rules Engine / world.toml / mods.lock 为长期社区服和玩法扩展提供价值。
- 当前不是玩法方向失败，而是仍有数值、体验、PvE/社交/新手路径缺口。

2/3 多数点:
- 首小时/新手路径、教程、AI 可学习路径需要更明确的产品化闭环（rev-gpt-designer + rev-dsv4-designer；rev-claude-designer从分层解锁角度支持）。
- PvE、社交/合作、经济 sink、catch-up mechanics 是 World 模式长期留存缺口（rev-dsv4-designer + rev-gpt-designer）。
- Overload 对 AI/human 或长期 meta 有不对称影响（rev-dsv4-designer + rev-claude-designer，Security 支持其 side-channel 风险）。

1/3 孤点或低共识点:
- rev-claude-designer 独立提出 Fortify 永动护盾、Controller repair cap 语义、age_max 无下限为玩法 Blocker。由于另外两个 Designer 未独立发现同一问题，Speaker 将其列为方向专属 High/Blocker，不升级为跨方向共识 Blocker，但建议编码前处理。
- rev-gpt-designer 独立强调“一键分享成内容”和 replay 产品规格。
- rev-dsv4-designer 独立强调 PvE 缺失为 High。

---

## 共识 Blocker（跨方向 + 跨模型同意）

### B1: Rhai / RuleMod 隔离模型与信任链未收敛

方向 × 模型矩阵:
- Architect: rev-gpt-architect A2；rev-claude-architect A7（能力白名单/爆炸半径）
- Security: rev-dsv4-security C1；rev-gpt-security H5；rev-claude-security C1

问题:
文档同时表达“Rhai 默认 process isolation”和“Bevy in-process add_systems/tick_end.call/actions.apply(world)”两套互斥架构。除此之外，模组签名、trusted_keys、mods.lock checksum、key revocation/expiry、RhaiActionBuffer 上限也没有形成闭环。实现者如果照 DESIGN 的 in-process 示例实现，会弱化 specs 中的隔离承诺；如果照 process isolation 实现，则现有 Bevy 示例和 replay/checksum/IPC 合同不足。

修正要求:
1. 明确 MVP Rhai 运行模式：in-process / process-isolated 二选一；若两者都支持，必须分别给出 hook 时序、IPC、determinism、timeout/kill、rollback 语义。
2. 删除或标注 DESIGN 中与默认 process isolation 矛盾的 Bevy in-process 示例。
3. 将 RuleMod action 应用改为 ActionBuffer → mini-validator → validate_and_apply/单一写路径，不允许绕过 combat/visibility/resource 管线。
4. `mods.lock.checksum` 设为必需；加入 signed_at、expires_at、revoked_keys/revoked_at、world.toml/mods.lock 文件权限和 signed commit 假设。
5. 为 RhaiActionBuffer 增加硬上限（大小、action 数、每类 action 数），超限语义必须 deterministic。

### B2: WASM 编译缓存、security_epoch、Wasmtime 安全门禁不一致

方向 × 模型矩阵:
- Architect: rev-claude-architect A3/A4；rev-gpt-architect missing ABI/schema hash handshaking
- Security: rev-claude-security C3；rev-gpt-security C2；rev-dsv4-security I4/相关 Wasmtime 版本锁定与回放关注

问题:
specs/04 与 specs/09 对编译缓存键给出不同定义；部分文档只按 `(module_hash, wasmtime_version)` 缓存，另一处包含 parser/policy/build/arch/security_epoch。若 security_epoch 或 validation policy bump 后缓存未全量失效，恶意模块可能停留在旧验证规则下。Wasmtime 固定 `=30.0` 也缺少“当前安全线 patch version + RustSec hard gate + backend policy”的硬合同。

修正要求:
1. 统一缓存键为 `Blake3(module_hash || wasmtime_build_commit || wasmparser_version || validation_policy_version || target_arch || security_epoch)`。
2. 明确 validation policy / parser / wasmtime build / target arch / security_epoch 任一变化都必须 invalidate cache。
3. 文档增加 security_epoch bump runbook：全量重编译窗口、降级模式、容量估算、SLA。
4. Wasmtime 不应写死过期 fixed version；改为“锁定到当前受支持安全线的 patch version”，CI 对 wasmtime/wasmparser/cranelift/wasi advisory fail closed。
5. 明确 compiler backend policy（如禁用 Winch，除非单独评审）和 x86_64/aarch64 支持矩阵。

### B3: 可见性、拒绝路径、snapshot/simulate 输出仍可形成信息泄露通道

方向 × 模型矩阵:
- Architect: rev-gpt-architect A4；rev-claude-architect H1/H5 类读源/可见性缓存关注；rev-dsv4-architect CG/edge clarification
- Security: rev-gpt-security C1/H2/H3；rev-claude-security H1/H2/H5/H6；rev-dsv4-security M1/I5

问题:
多个输出面可能绕过 fog-of-war：command validation rejection detail 先泄露 target existence/type/range/status；Phase 2a 内移动后可见性缓存语义不清；snapshot 256KB distance-first truncation 可被攻击者用廉价实体挤占；MCP full view、simulate/dry_run、replay/explain 接口如果不共享脱敏逻辑，会把“只读接口”转化为下一次 WASM deploy 的 gameplay 优势。

修正要求:
1. 所有 target_id 校验必须先执行 visibility check；不可见与不存在统一返回 opaque `NotVisibleOrNotFound`。
2. rejection detail 仅允许包含调用者自身信息、公开阈值、调用者已可见目标信息；admin trace 才能保留完整 detail。
3. 明确 Phase 2a 使用 tick 起始 frozen visibility cache，或明确重算规则；所有 command 一致。
4. Snapshot 截断改为分桶/权重：自身关键实体（Spawn/Controller/owned critical structures）不得被敌方廉价实体挤出；truncated=true 必须附带安全降级语义。
5. `swarm_simulate` / `swarm_dry_run_commands` / `swarm_get_replay` / `swarm_explain_last_tick` 必须共享玩家视图脱敏和范围/CPU/IO 上限。

### B4: host_path_find / host function 成本模型不是资源等价

方向 × 模型矩阵:
- Architect: rev-gpt-architect A3
- Security: rev-dsv4-security H2；rev-gpt-security host/simulate CPU boundary concern H3/M2

问题:
WASM 指令被 fuel metering，但 host_path_find 的服务端原生计算成本按返回 path length 或固定调用数估算，无法覆盖 explored nodes、不可达目标、障碍拓扑、cache miss、visibility mask 等真实 CPU 成本。攻击者可通过低 fuel 成本触发高服务器 CPU 计算，形成沙箱绕过。

修正要求:
1. host_path_find 成本必须按 explored_nodes / expanded_edges / cache_miss 等真实工作量计费，而非只按 path_length。
2. 增加 per-player/per-tick/per-room pathfinding CPU budget；超限 deterministic fail。
3. 对不可达路径、复杂迷宫、极端 visibility mask 增加测试向量。
4. 在 specs/04 与 specs/02 中统一 pathfinding 资源合同。

### B5: Overload 的静默 no-op、全局冷却和 fuel mutation 仍构成 side-channel / 公平性风险

方向 × 模型矩阵:
- Architect: rev-gpt-architect A6
- Security: rev-dsv4-security C2/H3；rev-gpt-security M1
- Designer: rev-dsv4-designer G3；rev-claude-designer meta concern

问题:
Overload 试图通过静默 no-op 防止攻击者获知目标 fuel floor，但攻击者仍可通过自身 cost、cooldown、目标行为变化、多方合谋、恢复速率公开信息推断目标状态。Designer 方向还指出 Overload 对 AI 的扰动强于人类，可能形成不对称 meta。

修正要求:
1. 明确 Overload 成功/地板/no-op 时攻击者 cost、cooldown、目标 global cooldown 是否完全一致。
2. 若继续保留 fuel attack，必须将所有可观测副作用等价化；否则改为非燃料型 debuff（例如 action throughput debuff）以降低 side-channel。
3. 对多方合谋和跨 tick repeated probing 写入安全测试。
4. Designer 方向需重新评估 Fortify/Disrupt/Overload counter loop，避免一个防御技能或一个 CPU attack 支配 meta。

### B6: refund/session/deploy_nonce 控制面状态机未闭合

方向 × 模型矩阵:
- Architect: rev-gpt-architect A5
- Security: rev-dsv4-security H1/M3；rev-gpt-security M4；rev-claude-security C2
- Designer: rev-claude-designer 提及 refund 滥用作为玩法漏洞背景

问题:
refund credit “同一 session 内部署不清除”的 session 生命周期、session_id 签发与不可伪造性、多 WASM slot 隔离未定义。deploy_nonce TTL 与编译队列、audience 绑定、atomic consume 未形成单一状态机。控制面含糊会直接影响计算预算、部署授权和重放安全。

修正要求:
1. 定义 session 生命周期、session_id 服务端签发方式、断连/重连/长期 agent 连接语义。
2. refund credit 限定到 player + wasm_slot + session + tick window；跨 slot/跨 audience 不得转移。
3. deploy_nonce 必须 single-use、audience-bound、world-bound、player-bound，建议默认 IP-bound；验证时必须匹配 request audience。
4. 编译时间超过 nonce TTL 时使用 server-side pending-deploy 状态机，而不是延长裸 nonce。
5. 所有状态转换写成表格并纳入 replay/audit。

### B7: Tick 执行、FDB/Bevy rollback、读源与广播失败矩阵仍不够硬

方向 × 模型矩阵:
- Architect: rev-claude-architect A1/A2/A5/A8；rev-gpt-architect A7/A8；rev-dsv4-architect D1/D3
- Security: rev-gpt-security M2；rev-claude-security H1/H6

问题:
Architect 组对 severity 有分歧：rev-dsv4-architect 认为 ECS RW 冲突可由 Bevy 自动序列化，rev-claude-architect 认为文档证明自相矛盾且可能影响 cooldown 语义。Speaker 不将“ECS 并行”单独升级为最高 Blocker，但将其并入 tick consistency Blocker：Phase 2a panic/OOM、FDB commit fail、Dragonfly rebuild、NATS publish fail、MCP_Query/read source、BROADCAST budget、output size 256KB/1MB 不一致，都需要单一失败矩阵。

修正要求:
1. specs/01 增加完整 failure matrix：COLLECT crash、Phase 2a panic/OOM、FDB commit fail、Dragonfly update fail、NATS publish fail、BROADCAST overload、replay write fail。
2. 明确每种失败对 Bevy World snapshot restore、FDB commit、Dragonfly cache、MCP/REST query read source 的影响。
3. 拆分或重命名 Cooldown 组件语义（SpawnCooldown vs ActionCooldown），或明确调度顺序并修正并行证明。
4. 统一 tick output / snapshot / trace size limit（256KB vs 1MB）并写入引用源。
5. 明确 MCP_Query/read API 的权威读源优先级。

---

## 方向专属 High 优先级

### A-H1: Dynamic CommandAction vs 强类型 IDL/SDK 边界

主要来源: rev-gpt-architect A1；Security 的 schema drift H4 支持。

处理: 需要设计裁决。MVP 推荐固定 Vanilla CommandAction enum；Experimental world 使用 `CustomAction { name, params, schema_hash }` envelope，不承诺官方 SDK 强类型。若选择 world-specific IDL，则必须引入 ABI/schema hash、world-specific SDK 发布、WASM ModuleManifest 校验。

### A-H2: 可观测性、容量规划、WASM ABI 演进文档缺失

主要来源: rev-claude-architect M1/M2/M5；rev-gpt-architect missing list。

处理: P0 文档补齐项。至少需要 metrics/export/alerts/runbook、500/5000 player 容量假设、WASM ABI/schema/hash migration 策略。

### S-H1: Wasmtime/rmcp/依赖安全硬门禁

主要来源: rev-gpt-security C2/H1；rev-claude-security C3；rev-dsv4-security I4。

处理: security/CVE-SLA 与 specs/04 补 hard gate：cargo audit/deny fail closed、rmcp DNS rebinding fixed version/deployment gate、feature flags 最小化、backend policy。

### S-H2: Endpoint 级 ACL、rate limit、range cap

主要来源: rev-gpt-security M3/H3；rev-claude-security H5；rev-dsv4-security I5。

处理: REST/WS/gRPC/MCP 每个 endpoint 列出 auth、audience、visibility scope、rate limit、payload/output cap、CPU/IO cap。`swarm_get_replay` 必须有 tick range 上限和分页。

### D-H1: Fortify 永动护盾、Controller repair cap、age_max 下限

主要来源: rev-claude-designer G1/G2/G5。

处理: 虽未达跨模型共识，但属于编码前低成本高收益修正。建议：Fortify 加 per-target cooldown 或不可刷新；Controller repair cap 以 idle natural aging=1.0 为基准写死；`age_max = max(MIN_LIFESPAN, base + modifiers)`，MIN_LIFESPAN 写入 world.toml。

### D-H2: Harvest/spawn/tower/source 核心数值缺失

主要来源: rev-claude-designer high_priority_missing；rev-gpt-designer first-hour loop；rev-dsv4-designer economy/catch-up concerns。

处理: 编码前必须补最小默认值：Work harvest rate、spawn cooldown、tower charge rules、source capacity 多资源合计算法。否则 MVP feedback loop 无法平衡。

### D-H3: PvE、社交/合作、catch-up、内容传播

主要来源: rev-dsv4-designer G1/M1-M4；rev-gpt-designer G4/G5/G7。

处理: 不阻塞 P0 engine freeze，但应进入 P1 产品/内容 backlog。World 模式若完全零和，长期留存风险高。

---

## Medium/Low 处置

| ID | 问题 | 负责 Phase | 处置 |
|---|---|---:|---|
| M/L-1 | “六邻”/TopRight 等方向残留 | Docs cleanup | 改为四邻/orthogonal；全局搜索 stale direction terms |
| M/L-2 | Drain continuous effect 与 per-tick action quota 关系 | Specs/02 | 写明 continuous effect 是否占 action quota |
| M/L-3 | Hack maturity vs Recycle 同 tick race | Specs/02 | 增加边界示例与测试 |
| M/L-4 | Tutorial 来源隔离在 Source Gate 中不够显式 | Specs/09 | 增加 Tutorial source capability row |
| M/L-5 | CollectCache retry fuel 语义 | Specs/01 | 明确 cache key、retry charge/no-charge 条件 |
| M/L-6 | Federation / multi-world causality | P1 architecture | 保留 placeholder，不阻塞 MVP |
| M/L-7 | Zero-downtime engine upgrade | P1 ops | 与 ABI migration/runbook 合并规划 |
| M/L-8 | Replay 一键分享、短视频/解说覆盖层 | P1 product | 纳入社区传播 backlog |
| M/L-9 | Arena solved-game risk / map variety | P1 game design | world.toml map seed/variant/banlist 机制规划 |
| M/L-10 | Code update cost = 0 的策略承诺问题 | P1 tuning | MVP 可保留，后续根据 meta 增加 world-configurable cost/cooldown |

---

## 文档维护项

1. 将所有 R3 review artifact 统一保留在 `/data/swarm/docs/reviews/R3/`；根目录遗留的 `review-rev-*.md` 若存在，应移动或删除，避免 Speaker 下一轮读到 stale duplicate。
2. 更新 `/data/swarm/docs/reviews/README.md`：添加 R3 verdict、9/9 完成状态、总体 REQUEST_MAJOR_CHANGES、共识 Blocker 列表。
3. 更新 `ROADMAP.md`：新增 R3 blocker closure plan，明确哪些是 P0 implementation gate，哪些是 P1 product backlog。
4. 修复文档路径命名不一致：`review-rev-claude-security.md` vs `rev-claude-security.md`，建议统一为 `rev-{model}-{direction}.md`。
5. R4 复审提示应聚焦 B1-B7 closure，不应重新引入历史 R1/R2 上下文；但可以要求 reviewers 专门验证 R3 blockers 是否闭合。

---

## 评审统计

### 3×3 Verdict / Severity 矩阵

| Direction | Claude Opus 4.7 | GPT-5.5 | DeepSeek V4 Pro |
|---|---|---|---|
| Architect | APPROVE_WITH_RESERVATIONS — 3 Blocker + 6 Missing | REQUEST_MAJOR_CHANGES — 3 blocking + 7 missing | APPROVE — low/doc fixes only |
| Security | REQUEST_MAJOR_CHANGES — 3 Critical + 6 High | REQUEST_MAJOR_CHANGES — 2 Critical + 5 High + 5 Medium | REQUEST_MAJOR_CHANGES — 2 Critical + 3 High + 4 Medium |
| Designer | APPROVE_WITH_RESERVATIONS — 3 gameplay Blocker + 4 High missing values | APPROVE_WITH_RESERVATIONS — 9 UX/product concerns | APPROVE_WITH_RESERVATIONS — 1 High + multiple Medium/P1 gaps |

### 共识强度评估

- 强共识（≥2 方向 + ≥2 模型）: B1 Rhai/mod isolation/trust；B2 WASM cache/epoch/Wasmtime gate；B3 visibility/rejection/snapshot/simulate leakage；B4 host_path_find resource equivalence；B5 Overload side-channel/fairness；B6 refund/session/deploy_nonce state machine；B7 tick/FDB/rollback/read-source matrix。
- 中等共识（方向内多数）: 新手路径/PvE/social/catch-up、endpoint rate limits、capacity/observability/ABI docs。
- 分歧: ECS RW 矩阵 severity（Claude/GPT 认为需修，DeepSeek 认为 Bevy 自动处理且非阻塞）；Fortify/age_max 是否为跨方向 Blocker（Claude Designer 强烈认为是，其他 Designer 未独立发现）。
- 无根本反对: 没有评审员要求 REJECT；没有评审员否定 WASM-only gameplay、MCP as management、World Rules Engine 的核心方向。

### R4 入场条件

R4 前最低要求：
1. B1-B7 全部有文档级修正或明确用户裁决。
2. D-H1/D-H2 中编码前必需的数值/边界补齐。
3. 根目录 review artifact 清理，R3 index 更新。
4. 复审时 9/9 reviewers 全量运行，重点验证 R3 blocker closure。

---

## 用户裁决（2026-06-16）

1. **B1 Rhai 隔离模型**：✅ in-process。Rhai 是服主安装的受信代码，嵌入引擎进程直接调 Bevy ECS。删除 specs 中矛盾的 process isolation 描述。保留信任链：mods.lock.checksum 必签、key 管理、ActionBuffer 硬上限。

2. **B5 Overload side-channel**：✅ 保持设计，三种结果 cost/cooldown 完全等价。成功、地板、no-op 消耗同等 300 Energy + 200 tick drone cooldown + 50 tick 全局冷却，返回统一 `Ok`。外部不可区分是否触及 fuel 地板。

3. **A-H1 CommandAction 扩展模型**：✅ 固定枚举。IDL 定义 Vanilla CommandAction enum，SDK 强类型。服主只能调参（cost/cooldown/damage），不能新增命令类型。新机制走 Rhai 模组注册，不走 world.toml custom_actions。

4. **D-H1 Fortify + age_max**：✅ 采纳。Fortify 加 per-target cooldown（防永动护盾）；age_max = max(MIN_LIFESPAN, base + modifiers)，MIN_LIFESPAN 写入 world.toml（默认 100 tick）。
