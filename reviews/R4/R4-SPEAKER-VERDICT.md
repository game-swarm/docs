# Swarm R4 设计评审 — Speaker 共识裁决

**任务**: R4 Speaker 共识裁决  
**输入**: `/data/swarm/docs/reviews/R4/` 下 9/9 评审报告  
**输出**: `/data/swarm/docs/reviews/R4/R4-SPEAKER-VERDICT.md`  
**Speaker**: rev-speaker  
**原则**: 仅综合 R4 原始评审报告；不读取旧评审、不重评设计本身。

---

## 一、裁决概要

R4 议会 9 名评审官全部完成：Architect 3/3、Security 3/3、Designer 3/3。总体信号是：R4 文档已经在若干基础架构合同上明显收敛，尤其是单一 `validate_and_apply()` 指令管线、WASM 沙箱、多源 Command Source Model、统一可见性函数、MCP Browser/Agent transport 拆分、Bevy↔FDB 回滚对称性等，均被多名评审员认可为成熟方向。

但 R4 仍未达到可冻结或可直接进入实现的状态。跨方向重复出现的问题集中在：Rhai/RuleMod 信任边界、tick/compute/fuel 预算、snapshot/truncation 可扩展性与可武器化、可见性/spectate/oracle 合同、Command schema 与部署身份链、以及特殊攻击/出生/生命周期玩法漏洞。这些问题不是单个评审员的孤立偏好，而是至少 2 个方向、至少 2 个模型反复指出的设计合同缺口。

**总体 Verdict: REQUEST_MAJOR_CHANGES**

**Freeze 状态**: 不建议 Freeze；不建议进入实现阶段。R5 入场前必须先修正所有共识 Blocker，并对方向专属 High 给出明确处置或延期理由。

---

## 二、3×3 Verdict 矩阵

| Direction | Claude Opus 4.7 | GPT-5.5 | DeepSeek V4 Pro |
|-----------|------------------|---------|-----------------|
| Architect | CONDITIONAL_APPROVE — 1 Critical, 2 High, 7 Medium, 4 Low, 6 Missing | CONDITIONAL_APPROVE — 5 High, 4 Medium, 1 Low | CONDITIONAL_APPROVE — 4 Medium, 5 Consistency Gaps, 3 Algorithmic Risks |
| Security | REQUEST_MAJOR_CHANGES — 4 Critical, 6 High, 7 Medium, 6 Low/Info | REQUEST_MAJOR_CHANGES — 6 High, 8 Medium, 6 Info | CONDITIONAL_APPROVE — 3 High, 5 Medium, 3 Low |
| Designer | CONDITIONAL_APPROVE — 3 Critical, 5 High, 7 Medium, 4 Low, 10 Missing | CONDITIONAL_APPROVE — 3 High, 4 Medium, 1 Low | CONDITIONAL_APPROVE — 1 High, 3 Medium, 3 Low |

**Verdict 分布**:
- REQUEST_MAJOR_CHANGES: 2/9（Security: Claude, GPT）
- CONDITIONAL_APPROVE: 7/9
- APPROVE / REJECT: 0/9

**强度评估**: Security 方向出现 2/3 REQUEST_MAJOR_CHANGES，且 Architect / Designer 也分别给出 Critical 或 High，因此 Speaker 不采纳 “仅条件批准” 的最低风险解释，裁定为 REQUEST_MAJOR_CHANGES。

---

## 三、方向内交叉评审摘要

### Architect 组

**赞同点 / 多数点**:
- Phase 2b 系统顺序、RW 矩阵、regeneration/combat 关系需要统一：rev-claude-architect A2，rev-dsv4-architect CG2/D2。
- Bevy snapshot / snapshot restore 是核心复杂度与扩展边界：rev-claude-architect A3，rev-dsv4-architect D1，rev-gpt-architect A1/A7。
- Rhai/RuleMod 信任与隔离模型仍有矛盾：rev-gpt-architect A3，rev-dsv4-architect D3。
- schema / hard-limit / 配额常量不一致会导致实现分叉：rev-gpt-architect A4，rev-dsv4-architect CG1/CG4/CG5，rev-claude-architect A8/A12。

**孤点但重要**:
- rev-claude-architect A1 tick 三阶段预算超过 3000ms 是架构组唯一 Critical；虽为单评审员 Critical，但与 Security 的 simulate/path_find/fuel 放大问题同属 compute budget 合同缺口，已升格到共识 Blocker B2。

### Security 组

**赞同点 / 多数点**:
- Rhai/RuleMod 信任边界、进程隔离、IPC/capability 模型必须修正：rev-claude-security C1/H1/H2，rev-gpt-security H1/H6，rev-dsv4-security M1。
- MCP simulate/dry-run/path_find 是计算放大入口：rev-claude-security H3/M2，rev-gpt-security H5/M5，rev-dsv4-security H2。
- 可见性 / spectate / oracle 合同仍有绕过或枚举风险：rev-claude-security C3/H5，rev-gpt-security H3，rev-dsv4-security M3。
- PRNG / seed rotation / forward secrecy 边界需明确：rev-claude-security C2，rev-gpt-security M4，rev-dsv4-security M5。

**分歧**:
- Claude Security 将 Rhai、world_seed、public_spectate、CommandIntent 判为 Critical；GPT Security 整体为 High；DSV4 Security 多数降为 Medium/High 并给出 CONDITIONAL_APPROVE。Speaker 裁定：其中跨方向重叠的问题升格为 Blocker；仅前向保密等安全专属问题保留为 Security High/Critical 专属项。

### Designer 组

**赞同点 / 多数点**:
- 特殊攻击系统复杂度与平衡风险明显：rev-claude-designer G2/G4/G7/G8，rev-gpt-designer G3，rev-dsv4-designer G5/G6/G7。
- 新手/first-hour/onboarding 仍不足：rev-gpt-designer G1/G2/G6，rev-dsv4-designer G3，rev-claude-designer G13。
- World 模式长期目标/胜利条件/身份追求不足：rev-gpt-designer G4，rev-dsv4-designer G4，rev-claude-designer G9。

**孤点但重要**:
- rev-claude-designer 的 3 个 Critical（出生即斩、Overload 永久压制、Recycle 末期滥用）未被另外两个 Designer 以同等严重度提出，但其中 Overload/Hack/Fabricate/Recycling 的一部分与 Architect/Security 对状态机、可见性、特殊攻击边界的担忧重叠，因此作为共识 Blocker B6 的核心证据之一。

---

## 四、共识 Blocker

### 🔴 B1 — Rhai / RuleMod 信任链、隔离与能力模型不一致

| 方向 | 评审员 | 原始 ID |
|------|--------|---------|
| Architect | rev-gpt-architect | A3 |
| Architect | rev-dsv4-architect | D3 |
| Security | rev-claude-security | C1, H1, H2 |
| Security | rev-gpt-security | H1, H6 |
| Security | rev-dsv4-security | M1 |

**共识强度**: 2/3 directions, 3/3 models。

**问题**: R4 同时表达了 “Rhai/RuleMod 是服主信任的规则模块”、“可 inprocess 执行”、“可进程隔离执行”、“不能绕过 Command Validation Pipeline”、“拥有 actions.* 能力” 等多组合同，但吊销、默认运行模式、IPC 协议、capability namespace、RuleMod 对实体/flag/世界状态的权限边界没有被统一成一个可实现模型。

**裁决**: Blocker。只要该合同未闭合，RuleMod 既可能成为供应链 RCE 面，也可能绕过核心玩法校验管线。

**修正要求**:
- 明确 RuleMod 默认运行模式：是否强制 out-of-process；若允许 inprocess，列出仅限开发/离线的条件并默认关闭。
- 定义 RuleMod trust chain：签名、版本 pin、CRL/吊销、epoch bump、operator override、回滚策略。
- 定义 RuleMod capability namespace：`actions.*` 可写范围、禁止项、审计字段、与 `validate_and_apply()` 的关系。
- 若 RuleMod 可以影响世界状态，必须说明其是 “世界规则系统” 还是 “玩家命令旁路”；禁止语义模糊。

---

### 🔴 B2 — tick / fuel / simulate / path_find 计算预算合同不可执行

| 方向 | 评审员 | 原始 ID |
|------|--------|---------|
| Architect | rev-claude-architect | A1, A11 |
| Architect | rev-gpt-architect | A6 |
| Architect | rev-dsv4-architect | CG4, CG5 |
| Security | rev-claude-security | H3, M2 |
| Security | rev-gpt-security | H5, M5 |
| Security | rev-dsv4-security | H2 |

**共识强度**: 2/3 directions, 3/3 models。

**问题**: R4 的计算预算散落在 tick interval、COLLECT timeout、EXECUTE timeout、FDB retry、WASM fuel、host function fuel、MCP simulate/dry-run、path_find cache 等多个合同中，但缺少统一的墙钟/CPU/fuel/IO 预算模型。结果是：单 tick 理论预算可超过 3000ms，simulate/dry-run 可成为放大入口，path_find 可被 adversarial map 触发 DoS，跨重试 fuel 扣费来源不清。

**裁决**: Blocker。该问题同时影响架构可调度性、安全抗 DoS、玩家公平性和实现验收。

**修正要求**:
- 定义 tick interval 是目标、软上限还是硬上限；定义 tick overrun 后是否阻塞、跳 tick、降级或丢弃。
- 建立统一预算表：COLLECT、EXECUTE、BROADCAST、FDB retry、simulate、dry-run、path_find、host function、compilation。
- 明确 MCP simulate/dry-run 与 Arena/World 的配额差异，统一 specs/04 与 specs/09。
- 定义 host function fuel 扣费协议，尤其是 `path_find` 的 explored_nodes / expanded_edges / cache_miss 扣费与上限。
- 明确 COLLECT 缓存复用时的 `consumed_fuel` 语义，禁止重试绕过预算。

---

### 🔴 B3 — Snapshot / truncation / restore 模型既不可扩展又可被武器化

| 方向 | 评审员 | 原始 ID |
|------|--------|---------|
| Architect | rev-claude-architect | A3 |
| Architect | rev-gpt-architect | A1, A7 |
| Architect | rev-dsv4-architect | D1, AR2 |
| Security | rev-dsv4-security | H1, M2 |
| Security | rev-claude-security | M2 |

**共识强度**: 2/3 directions, 3/3 models。

**问题**: Bevy World 深拷贝 snapshot/restore 被用于 FDB commit 回滚，但其规模上限、墙钟预算、内存预算、copy-on-write/增量方案未定义；同时 256KB snapshot truncation 会影响玩家模型稳定性，并可能被玩家通过实体布局、出口视野、path_find/cache 等手段武器化。

**裁决**: Blocker。该问题不是单纯性能优化，而是影响确定性、安全和 Tier 2 扩展承诺的架构合同。

**修正要求**:
- 为 full snapshot 模型声明适用规模与预算上限，例如仅 Tier 1/MVP 有效。
- 若保留 Tier 2 目标，补充 incremental snapshot / modification set / copy-on-write 迁移路径。
- 定义 truncation 的确定性排序、保留优先级、玩家可预期性、滥用检测与测试向量。
- 明确 snapshot 构建与 WASM 执行、FDB commit、MCP query 的并发/时序边界。

---

### 🔴 B4 — 可见性、spectate、oracle 与 MCP 查询边界仍未闭合

| 方向 | 评审员 | 原始 ID |
|------|--------|---------|
| Architect | rev-gpt-architect | A5 |
| Architect | rev-dsv4-architect | D4 |
| Architect | rev-claude-architect | A5, A7 |
| Security | rev-claude-security | C3, H5, L4 |
| Security | rev-gpt-security | H3 |
| Security | rev-dsv4-security | M3 |

**共识强度**: 2/3 directions, 3/3 models。

**问题**: R4 已有统一 `is_visible_to()` 的正确方向，但多名评审员仍指出边界不闭合：public_spectate + spectate_delay 可能绕过 fog_of_war，MCP 查询与 WASM snapshot 有 tick 时差，Overload “三结果等价”仍可能从目标实体视角形成 oracle，`NotVisibleOrNotFound` 与 IDL/校验矩阵存在冲突，跨房间出口视野可扩大 snapshot 面。

**裁决**: Blocker。可见性合同是游戏公平、安全和 replay/spectate 产品化的共同根基，不能留给实现阶段自由发挥。

**修正要求**:
- 声明 invariant：WASM snapshot 永远只见 `fog_of_war` 过滤结果；public_spectate/player_view/replay 不能反向影响玩家输入面。
- 定义 public_spectate 的权限、延迟、竞技模式默认值、是否允许 full-map、是否可被匿名访问。
- 给所有 MCP/REST/WebSocket/replay 输出面列出是否调用 `is_visible_to()` 及 tick 基准。
- 为 `swarm_get_snapshot` 增加或等价定义 `snapshot_tick`，说明它与 WASM tick input 的时间关系。
- 为 Overload/Hack 等特殊攻击定义从 attacker 与 target 两侧可观察到的等价性/非等价性。

---

### 🔴 B5 — Command schema、source ordering 与部署身份链存在实现分叉风险

| 方向 | 评审员 | 原始 ID |
|------|--------|---------|
| Architect | rev-gpt-architect | A4 |
| Architect | rev-claude-architect | A8, A12 |
| Architect | rev-dsv4-architect | CG1, CG5 |
| Security | rev-claude-security | C4, H4, L2 |
| Security | rev-gpt-security | H2, M1, M2, M7 |

**共识强度**: 2/3 directions, 2/3 models。

**问题**: CommandIntent / RawCommand / ValidatedCommand 与 source matrix 的边界仍有多处可导致实现分叉：`additionalProperties` 不一致造成字段注入风险，`sequence` 跨 source 排序未定义，main action quota 缺拒绝码与 refund 策略，部署证书/密钥所有权模型与 JWT audience/transport 拆分存在冲突，Tutorial/Admin/Replay 路由规则不完全一致。

**裁决**: Blocker。该问题直接影响身份不可伪造、审计链、命令排序确定性和客户端 SDK 生成。

**修正要求**:
- 统一所有 JSON schema 的 `additionalProperties`，默认拒绝未知字段；列出唯一例外。
- 定义 `sequence` 是 per-player、per-source 还是 per-(player,source)，并同步排序 key。
- 增加 `MainActionQuotaExceeded` 或等价拒绝码，定义 refund 与覆盖/拒绝语义。
- 统一部署证书所有权：player key、agent key、server-issued certificate、nonce、CRL、epoch 的关系。
- 补齐 JWT `aud` / transport audience / Browser-vs-Agent header 判定合同。

---

### 🔴 B6 — 特殊攻击、出生保护与生命周期经济存在跨层级玩法漏洞

| 方向 | 评审员 | 原始 ID |
|------|--------|---------|
| Designer | rev-claude-designer | G1, G2, G3, G4, G7, G8, G14, M1 |
| Designer | rev-gpt-designer | G3 |
| Designer | rev-dsv4-designer | G5, G6, G7 |
| Architect | rev-claude-architect | A9 |
| Architect | rev-dsv4-architect | D4 |
| Security | rev-claude-security | L4 |
| Security | rev-dsv4-security | M3 |

**共识强度**: 3/3 directions, 3/3 models；Designer 方向内 3/3 同意特殊攻击/边界需收敛。

**问题**: 特殊攻击生态是 R4 的最大 gameplay 风险面。Designer 组指出出生即斩、Overload 永久压制、Recycle 末期滥用、Hack/Fabricate/Drain 经济性与反制窗口问题；Architect/Security 同时指出 Hack 状态机 system 归属、Overload 可见性引用语义、状态可见性与 oracle 风险不清。

**裁决**: Blocker。该问题不仅是数值平衡；它涉及 tick 系统归属、状态机推进、可见性、经济闭环和玩家 meta，一旦编码后再改成本高。

**修正要求**:
- 明确 spawn 当 tick 是否可被攻击；若可，给出反出生即斩机制；若不可，定义 grace 状态及持续时间。
- 为 Hack/Overload/Fabricate/Drain/Recycle/Leech 建立状态机、优先级、同 tick 多命中矩阵、cooldown 与反制窗口。
- 修正或证明 Overload 不会被多攻击者维持永久 fuel 锁死。
- 修正或证明 Recycle 不会在 lifespan 末期绕过 aging/death 经济约束。
- 将 `status_advance_system` 或等价系统纳入 Phase 2b 调度，并说明 owner 切换与原 owner 命令校验的关系。

---

## 五、方向专属 High / Critical 优先级

| ID | 来源 | 问题 | 裁决 | 时限 |
|----|------|------|------|------|
| A-H1 | Architect | Phase 2b regeneration/combat/death_cleanup 顺序在 DESIGN/specs/01/specs/07 不一致 | 已并入 B5/B2 的实现分叉风险；必须同步修正文档 | R5 前 |
| A-H2 | Architect | Tier 3 分片架构无 spec，仅有远期声明 | 不作为 R5 Blocker；需列入 Phase 1+ Architecture Backlog | Phase 1 设计前 |
| A-H3 | Architect | Engine startup/recovery runbook 缺失 | 高优先文档维护项；不阻塞 R5 但阻塞生产化 | Phase 1 前 |
| S-H1 | Security | world_seed / PRNG seed 前向保密边界 | 安全专属高风险；至少定义 seed rotation threat model 与泄露后影响 | R5 前 |
| S-H2 | Security | TickTrace 写入失败仅告警，审计完整性不足 | 不作为设计 Blocker；需补审计完整性链或降级语义 | Phase 1 前 |
| S-H3 | Security | seccomp / fd / clone / write sandbox OS 边界过宽 | 实现期安全基线；需转为 sandbox checklist | WASM sandbox 实现前 |
| D-H1 | Designer | first-hour fun / AI deploy onboarding 未闭环 | 不阻塞架构修订，但阻塞可玩 MVP；需补 onboarding loop | MVP playtest 前 |
| D-H2 | Designer | World 长期目标 / victory condition / identity goal 不足 | 保留为 game design high；不要求 World 模式强制胜利条件，但需声明长期追求 | MVP playtest 前 |
| D-H3 | Designer | Move-as-action 改变游戏手感 | 方向专属 High；需 playtest 或设计说明，不升为共识 Blocker | Balance pass |

---

## 六、Medium / Low 处置

| ID | 问题 | 负责 Phase | 处置 |
|----|------|-----------|------|
| M-01 | code propagation 与 spawn 时序边界 | R5 doc patch | 定义新生 drone 的 code_version 来源 |
| M-02 | refund credit 同 session deploy-reset 例外 | R5 security/economy patch | 移除例外或加累计上限 |
| M-03 | 跨房间出口视野扩展 | R5 visibility patch | 纳入 B4 修正范围 |
| M-04 | MCP tool concurrency model | Phase 1 API design | 定义 deploy/simulate/replay 互斥与资源池 |
| M-05 | in-flight deployment 降级语义 | Phase 1 ops/spec | 定义 nonce/compiling 状态在 degraded mode 下处理 |
| M-06 | Rhai version pinning / AST 兼容 | Phase 1 determinism | 加入 determinism version matrix |
| M-07 | audit log retention vs deletion rights | Phase 1 compliance | 定义删除请求、匿名化与完整性链并存策略 |
| M-08 | prompt injection delimiter 覆盖所有 AI 可见文本 | R5 security patch | 补足 player/mod/user strings 输出面 |
| M-09 | replay 第三方 git 仓库可用性 | Phase 1 replay design | 定义 vendoring/cache/fallback |
| M-10 | Tower / active aging / market abuse / occupancy / fatigue 数值 | Balance pass | 进入模拟与 playtest，不阻塞 R5 |
| M-11 | Arena rating/self-play/tournament | MVP+ competitive design | 单独出 Arena 评分 spec |
| M-12 | world selection 信息架构 | UX phase | 进入 UI/UX backlog |

---

## 七、文档维护项

R4 Speaker 不直接修改设计文档，但建议下一轮修订至少覆盖以下维护项：

- 在 specs/01、specs/04、specs/09 之间统一 tick/fuel/simulate/path_find 预算与配额。
- 在 specs/01、specs/07、DESIGN 中统一 Phase 2b 调度图，特别是 regeneration/combat/death_cleanup/status_advance。
- 在 specs/02、specs/08、specs/09 中统一 CommandIntent schema、`additionalProperties`、sequence/source sorting、拒绝码。
- 在 specs/03、specs/05、replay/spectate 相关章节中统一可见性输出面和 tick 时序。
- 在 RuleMod/Rhai 章节中新增或重写 trust chain / capability / isolation / CRL / IPC 合同。
- 在 Designer 相关章节中补特殊攻击状态机矩阵与 spawn/recycle/overload 生命周期约束。

---

## 八、R5 入场条件

- [ ] B1 Rhai / RuleMod 信任链、隔离与能力模型已统一。
- [ ] B2 tick / fuel / simulate / path_find 预算模型已统一，并可被实现验收。
- [ ] B3 snapshot / truncation / restore 的规模、确定性与滥用防护已明确。
- [ ] B4 可见性 / spectate / oracle / MCP query 输出面合同已闭合。
- [ ] B5 Command schema / source ordering / 部署身份链已统一。
- [ ] B6 特殊攻击、spawn 保护、Recycle/Overload/Hack 状态机已补齐。
- [ ] Security 专属的 seed forward secrecy threat model 已明确接受、修正或降级。
- [ ] Designer 专属的 first-hour/onboarding 与 World 长期目标至少有明确 MVP 处置路线。

---

## 九、未解决分歧与用户裁决点

### D-1: Rhai inprocess 是否允许作为生产模式

Security 倾向强制 out-of-process；部分架构表述似乎允许 inprocess。需用户/项目 owner 裁定：生产环境是否禁止 inprocess RuleMod。

### D-2: World 模式是否需要显式 victory condition

Designer 组有 2/3 指出长期目标不足；但 World 模式也可被设计成 Minecraft-like persistent sandbox，不必有胜利条件。需用户裁定：World 的长期追求是 leaderboard/progression，还是 sandbox identity/social goal。

### D-3: 新生 drone 是否应当同 tick 参与战斗

Architect 报告认可 “出生即投入战斗” 是当前设计意图；Claude Designer 判定为 Critical 漏洞。需设计裁决：保留即时战斗并加防护，还是延迟到下一 tick。

### D-4: Tier 2/Tier 3 扩展承诺是否属于当前冻结范围

Architect 对 snapshot 与 sharding 有强烈担忧。需裁定 R5 是否只冻结 MVP/Tier 1，还是要求 Tier 2/Tier 3 路线同时达到 spec-ready。

---

## 十、Speaker 结论

R4 已经从 “基础合同缺失” 收敛到 “关键合同仍需统一” 的阶段。多数评审员认可核心方向，但 Security 方向 2/3 给出 REQUEST_MAJOR_CHANGES，且 Architect/Designer 均存在 Critical/High 级阻塞项。Speaker 裁定本轮不能 Freeze，不能进入实现。

**最终 Verdict: REQUEST_MAJOR_CHANGES**

下一步建议：先按 B1–B6 做一次集中合同修订，再启动 R5。R5 的 prompt 应要求评审员只判断这些 Blocker 是否闭合，并限制输出为 APPROVE / CONDITIONAL_APPROVE / REQUEST_MAJOR_CHANGES，避免重新展开无边界 brainstorming。
