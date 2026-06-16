# Swarm 设计评审 R2 — Speaker 共识报告

> Speaker: rev-speaker  
> 输入范围: 仅 `/data/swarm/docs/reviews/R2/` 下 9 份评审：3 Architect、3 Security、3 Designer。  
> 注意: 本报告未读取 `/data/swarm/docs/reviews/` 下旧轮次文件，也未读取旧 Speaker Verdict。个别评审自身引用了旧轮次，这是评审员输入差异；Speaker 合成只以 R2 九份产物为依据。

---

## 裁决概要

R2 的总体信号高度收敛：9/9 评审均承认核心方向正确——AI/人类统一 WASM、MCP 不作为 gameplay controller、Source Gate 注入身份、`is_visible_to` 单一可见性边界、COLLECT/EXECUTE/BROADCAST tick 分层、FDB 权威源 + Bevy 工作副本，均被多个方向认为是正确骨架。

但 R2 仍不是可直接冻结并进入无保留实现的状态。主要风险不是“设计方向错误”，而是：

1. DESIGN 层的正确合同没有完整同步到 specs/IDL/API；
2. 若实现者按 specs/IDL 生成代码，仍可能复活 R1 已试图关闭的漏洞；
3. 安全方向新增了部署签名重放、Phase 2a TOCTOU、snapshot 输入 DoS 等实现前必须写入合同的攻击面；
4. Designer 方向认为核心可开工，但首发体验、Vanilla 分层、AI curriculum、Arena 产品闭环仍未达到“公开测试冻结”。

Freeze 状态：

- Architecture core: 可接受，但需先完成 spec convergence gate。
- Security: 不可冻结；至少 4 类安全合同需实现前闭合。
- Designer: 核心玩法骨架可继续；首发体验不可冻结。

---

## 总体 Verdict

**REQUEST_MAJOR_CHANGES**

含义：R2 的架构方向通过，但文档/合同层仍存在跨方向共识 Blocker。必须先做 R2 convergence patch，再进入实现冻结。若只问“能否继续探索/局部原型”，答案是可以；若问“能否按当前 specs 开始正式实现”，答案是否。

---

## 3×3 Verdict / Severity 矩阵

| Direction × Model | Claude Opus 4.7 | GPT-5.5 | DeepSeek V4 Pro |
|---|---|---|---|
| Architect | APPROVE_WITH_RESERVATIONS；Critical A1/A2，High A3-A5 | REQUEST_CHANGES；Blocker A1-A3，High A4-A7 | APPROVE_WITH_RESERVATIONS；D1-D5 must-fix，N1-N5 |
| Security | CONDITIONAL_APPROVE；Critical 2，High 4 | REQUEST_MAJOR_CHANGES；Critical 3，High 6 | CONDITIONAL_APPROVE；Critical 2，High 4 |
| Designer | APPROVE_WITH_RESERVATIONS；High G1-G3 | CONDITIONAL_APPROVE；High G1-G4 | APPROVE_WITH_RESERVATIONS；High G1-G2，Medium-High G3 |

收敛强度：

- 9/9 认可核心架构方向。
- 6+/9 直接或间接标记 Overload 合同未闭合。
- 5+/9 标记 specs/IDL/API 与 DESIGN 分裂会导致实现错误。
- 3/3 Architect 均要求先做 Spec Convergence Patch。
- 3/3 Security 均认为安全骨架正确但实现前仍有阻断项。
- 3/3 Designer 均认为核心玩法可继续，但首发/公开测试体验不能冻结。

---

## 方向内交叉评审

### Architect 组

3/3 赞同点：

- 核心架构方向正确：WASM 唯一执行器、MCP 非 gameplay、Source Gate、visibility 单函数、tick 分层、FDB 权威源均成立。
- specs/IDL 与 DESIGN split-brain 是 R2 最大架构风险。
- Overload 合同未同步到 specs/02 + specs/08。
- Direction enum / 世界拓扑不一致会污染 SDK 与实现。
- Tick Phase 2b schedule / 并行语义必须有唯一 canonical contract。
- Command limits 必须有单一权威常量。

2/3 多数点：

- Snapshot/rollback 成本需要 acceptance benchmark 或 mutation journal fallback（GPT + DSV4；Claude 也从规模拐点方向支持）。
- Core IDL 与 World Action Manifest 应拆层（GPT 明确提出，Claude 给出 replay-safe manifest hash，DSV4认可三层扩展模型）。
- MCP transport 不应长期写死为“仅 HTTP/SSE”（GPT + DSV4）。

1/3 孤点但重要：

- Claude Architect A1: FDB commit 与 BROADCAST 之间的 read-committed / crash window 未定义。
- Claude Architect A5: Auth Service epoch 与紧急轮换 runbook 缺失。
- DSV4 Architect N3: “Blake3 签名”表述混淆。

### Security 组

3/3 赞同点：

- 安全骨架正确，但 spec 层仍未达冻结。
- Overload 静默结果合同仍可能被 `TargetFuelTooLow`、validator、TickTrace/replay 泄露打破。
- 部署签名模型需要 nonce/temporal binding/CRL 或更清晰的证书模型。
- Phase 2a inline command loop 的原子性/TOCTOU 需要写入合同。
- Snapshot / command / audit 大字段需要明确大小上限与截断策略。

2/3 多数点：

- 编译缓存键必须包含 wasmparser / validation_policy / security epoch（Claude + DSV4，GPT 以 Wasmtime emergency playbook 支持）。
- MCP browser/non-browser transport contract 与 DNS rebinding 测试矩阵需补齐（GPT 强烈，DSV4/Architect 侧有弱支持）。
- Spectator / public_spectate delay 示例和 validate_config 需要闭合（GPT + Architect/Designer 交叉支持）。

1/3 孤点但需保留：

- DSV4 Security CRITICAL-1: RespawnPolicy 仍出现 Spectate/Ban。
- GPT Security H-6: `player_view=full` + deploy scope 可能构成 out-of-band 情报注入。
- Claude Security MED-1: TickTrace 与 world_seed/RNGState 同存可能破坏 shuffle 不可预测性。

### Designer 组

3/3 赞同点：

- “世界只认 WASM”是强公平性与社区信任核心卖点。
- 核心玩法骨架可继续实现，但首发体验不能冻结。
- Vanilla / 教程 / 新手路径需要 progressive reveal，不能第一小时暴露完整复杂度。
- Direction enum 六边形残留会破坏新手 mental model。

2/3 多数点：

- First Hour Journey / failure recovery / long-term identity / Arena product spec 需要文档化（GPT + Claude）。
- Vanilla 特殊攻击默认范围过宽，应分 Tutorial/Novice/Standard/Advanced（GPT + DSV4，Claude也支持平衡矩阵/首发前定型）。
- Overload 不只是安全合同问题，还有长期压制/恢复/间接信息泄露的玩法问题（Claude + DSV4）。
- Arena precommit / rating / match flow 不足（GPT + DSV4/Claude）。

1/3 孤点但有设计价值：

- DSV4 Designer: Fortify 纳什陷阱，Fortify 同时 counter 过多特殊攻击。
- DSV4 Designer: World PvE→PvP 激励梯度缺失，可能退化为龟缩 dominant strategy。
- GPT Designer: Replay 需要 share card / auto-highlight / weekly digest，否则难传播。

---

## 共识 Blocker（跨方向 + 跨模型同意）

### B1: Overload 安全合同仍 split-brain，且同时影响安全、公平性与玩法平衡

**方向 × 模型矩阵**:

- Architect: rev-claude-architect（confirmed D1-D5）、rev-gpt-architect A1、rev-dsv4-architect D1/N1
- Security: rev-claude-security 同意 dsv4 critical、rev-gpt-security C-1、rev-dsv4-security CRITICAL-2/HIGH-3/MED-4
- Designer: rev-claude-designer G1/G2、rev-dsv4-designer G3，rev-gpt-designer 间接支持 visibility/spectator trust

**问题**:

DESIGN 已要求 Overload 满足 visibility、同目标 50 tick 全局冷却、静默结果；但多个 R2 评审指出 specs/02、specs/08、api/commands 仍可能保留 `TargetFuelTooLow` / `target_fuel_above(0.2)` / 无 `visible_target` / 无 `target_global_cooldown`。这会让实现者按 specs/IDL 复活远程 fuel DoS 与 fuel 状态侧信道。Designer 还指出：即使直接返回静默，Overload 的恢复机制、Fortify 交互、TickTrace/replay 暴露仍可能形成长期压制或间接信息泄露。

**修正要求**:

1. specs/02 §3.12 删除 WASM 可见的 `TargetFuelTooLow` 拒绝语义；低于下限时 apply 阶段静默 no-op / clamp，外部结果统一。
2. specs/02 §3.12 增加 `target_visible` / `is_visible_to(...)` 与 `target_global_cooldown(50)`。
3. specs/08 Overload validator 删除 `target_fuel_above(0.2)` 作为拒绝条件，改为 `visible_target` + `target_global_cooldown(50)` + apply 内部 fuel floor。
4. 明确 global cooldown key：至少包含 `world_id + target_player_id -> last_overloaded_tick`，并定义 cooldown 命中时是否消耗攻击者 drone cooldown。
5. `TargetFuelTooLow` 若保留，只能是 admin/internal audit reason，不得进入 WASM response、public replay、普通 TickTrace。
6. 定义 Overload 与 Fortify/Purge/fuel recovery 的设计合同：fuel 减少是永久、可恢复、还是可净化；若可恢复，给出恢复曲线。
7. API docs / SDK examples / TickTrace / replay privacy 同步更新。

---

### B2: DESIGN / specs / IDL / API 的 spec convergence 未完成，当前仍会让实现者按不同文档实现出不同系统

**方向 × 模型矩阵**:

- Architect: 3/3 明确提出 split-brain；rev-gpt-architect verdict 直接为 REQUEST_CHANGES
- Security: rev-gpt-security C-1/C-2/C-3，rev-claude-security 同意 specs 层未关闭攻击面，rev-dsv4-security 给出 residual audit
- Designer: rev-claude-designer G7、rev-gpt-designer G9、rev-dsv4-designer cross-reference 支持

**问题**:

R2 多处关键合同存在“设计总览正确，executable spec/IDL 未同步”的状态。最典型包括 Overload、Direction、Tick schedule、Command limits、spectate_delay、Core IDL vs World Action Manifest。对于 Swarm 这种 deterministic/replayable/fairness-sensitive 系统，spec split-brain 不是文档洁癖，而是实现路径分叉。

**修正要求**:

1. 建立 R2 Spec Convergence Patch，至少覆盖：Overload、Direction、Tick schedule、Command limits、spectate_delay、Core IDL vs World Action Manifest。
2. 明确文档权威层级：DESIGN = 背景与设计意图；specs/IDL/generated constants = 实现合同；ROADMAP = 状态追踪，不得作为实现真相源。
3. 增加 docs/spec consistency smoke checks：Direction enum、RejectionReason、command limits、forbidden MCP gameplay tools、tick schedule 关键 schema 必须自动比对。
4. ROADMAP 的 ✅ 状态必须绑定一致性检查与测试证据，不能只表示“已写过文档”。

---

### B3: Tick mutation semantics 不完整：Phase 2a inline TOCTOU 与 Phase 2b schedule/RW matrix 均阻塞确定性实现

**方向 × 模型矩阵**:

- Architect: rev-claude-architect A2，rev-gpt-architect A3，rev-dsv4-architect D4
- Security: rev-claude-security CRITICAL-B，rev-dsv4-security HIGH-2，rev-gpt-security C-2/DoS 边界相关
- Designer: Claude/DSV4 从 Hack/Overload/Fortify 交互侧提出玩法后果

**问题**:

Architect 组聚焦 Phase 2b：DESIGN 与 specs/01 对 regeneration/combat/decay/death_cleanup 的顺序和并行语义不一致，且缺 Component/Resource 读写矩阵。Security 组聚焦 Phase 2a：逐条 validate+apply 的 inline 模型未定义原子性，导致 Hack friendly-fire、Spawn pending 可见性、Transfer chain resource amplification 等 TOCTOU/经济漏洞。

**修正要求**:

1. 选择唯一 canonical tick schedule，并同步 DESIGN + specs/01 + tests。
2. MVP 阶段建议采用全 `.chain()` 串行 schedule；若保留并行，必须先给出 Component/Resource 读写矩阵。
3. specs/02 明确 Phase 2a inline command loop 语义：
   - Spawn pending entity 对同 tick 后续命令不可见；
   - Hack 状态下原 owner 的 friendly/attack/recycle 规则；
   - per-drone per-tick main action quota / fatigue，防止 Transfer/Withdraw 链式放大；
   - fuel exhausted / wall-clock timeout / crash 均不读取 partial output。
4. CI 增加 schedule graph / conflicting access 验证；所有影响状态的 query 结果必须 deterministic sort 或明确 storage order contract。

---

### B4: WASM 部署签名与证书生命周期不具备防重放/吊销/审计闭环

**方向 × 模型矩阵**:

- Security: rev-claude-security CRITICAL-A，rev-gpt-security H-2，rev-dsv4-security HIGH-1
- Architect: rev-dsv4-architect N3，rev-claude-architect A5

**问题**:

当前部署签名描述存在多层混淆：`Blake3(WASM bytes)` 被写成“私钥签名”的对象，但没有 nonce、timestamp、world_id、player_id、module slot、version tag、server challenge 等防重放字段；证书吊销与编译缓存清除也未形成闭环。Auth Service compromise 的爆炸半径未受 epoch/CRL/runbook 限制。

**修正要求**:

1. 选择并写死部署认证模型：
   - 客户端 Ed25519 keypair + 服务端签 public key 证书；或
   - 无客户端签名，仅 bearer/mTLS + server-side audit。不得两套表述并存。
2. 若采用签名：payload 至少包含 domain separator、module_hash、player_id、world_id、module_slot/version_tag、deploy_nonce、expires_at。
3. `deploy_nonce` 由服务端签发，短 TTL，单次消费。
4. 定义 CRL 查询点：deploy 时、tick 执行前、module cache validation 时。
5. 编译缓存键加入 `wasmparser_version` / `validation_policy_version` / `wasmtime_build_commit` / `target_arch` / `security_epoch`，缓存只跳过编译，不跳过验证。
6. Auth Service 增加 epoch 与 emergency bump runbook；TickTrace 部署事件记录证书 epoch / cert fingerprint。

---

### B5: Public/MCP/spectator 输出面仍有现实信息泄露与 DNS rebinding 风险

**方向 × 模型矩阵**:

- Security: rev-gpt-security C-3/H-1/H-6，rev-claude-security HIGH-2，rev-dsv4-security HIGH-3
- Architect: rev-gpt-architect A9，rev-dsv4-architect H3/D3，rev-claude-architect A6 相关 fan-out 降级
- Designer: rev-gpt-designer G8，rev-claude-designer G1/G7 间接支持 visibility trust

**问题**:

MCP transport 仍以 “HTTP/SSE” 表述为主，browser Web UI 与 non-browser AI/CLI 的安全合同未拆清；DNS rebinding / Origin / Host / SNI / Fetch Metadata / token audience 的测试矩阵缺失。旁观配置方面，World public spectate 的 `spectate_delay >= 50` 约束与示例/validate_config 不完全闭合，可能导致实时全图泄露。公开旁观 owner/player_id 与 replay/TickTrace 中的 Overload outcome 也可能破坏信息边界。

**修正要求**:

1. specs/03 拆分 Browser Web UI 与 MCP agent/CLI transport contract：browser 走严格 Origin/Host/CSRF/Fetch Metadata；agent/CLI 走 mTLS 或 signed request，不依赖 Origin。
2. Token `aud` 绑定 gateway_origin + world_id + transport_class。
3. 增加 DNS rebinding / loopback / private-network / SSE reconnect 测试矩阵。
4. World 模式 `public_spectate=true` 时 `spectate_delay < 50` 必须 validate_config error 或强制 clamp，并修正所有示例。
5. Public spectator 默认 owner anonymization（salted per session 或配置化），避免长期去匿名化。
6. Replay / TickTrace 对非 admin 过滤 Overload 内部 outcome、rejection detail、大字段与 untrusted string。

---

### B6: Snapshot / simulation / audit 大小与成本边界未封住，存在 DoS 与工程预算失真

**方向 × 模型矩阵**:

- Security: rev-claude-security HIGH-3，rev-dsv4-security HIGH-4，rev-gpt-security H-3/M-2/M-5
- Architect: rev-gpt-architect A6，rev-dsv4-architect N4/N5，rev-claude-architect A4/A6

**问题**:

WASM 输出有 256KB cap，但输入 snapshot、host query result、simulate/dry-run、audit/TickTrace 大字段缺少同等严格的 caps 与截断语义。攻击者可通过堆实体放大对手 snapshot，或通过 MCP simulate/dry_run 把 engine 当计算资源。Architect 组也指出 full Bevy World snapshot/restore、FDB commit、BROADCAST fan-out 在 1000+ 玩家时需要性能闸门。

**修正要求**:

1. specs/01/specs/04 增加 per-player snapshot byte cap，建议 256KB；超限稳定排序截断，返回 `truncated` / `omitted_count`。
2. `host_get_objects_in_range` 返回 `{items, truncated, total_visible_count?}`，path_find 增加 `MAX_EXPLORED_NODES`。
3. MCP online simulate 限制 max_ticks/max_entities/max_output/max_cpu_ms/max_fuel_per_hour；长模拟只能本地 CLI 或异步隔离 worker。
4. Audit / TickTrace 大字段使用 hash + truncated preview，不记录完整 RawCommand body；所有 untrusted string 有长度上限与 escaping。
5. 建立 Phase 1/4 performance gates：snapshot+restore p95/p99、FDB commit p99、1000-player stress、fan-out backlog 压测。

---

## 方向专属 High 优先级

### A-H1: Commit → BROADCAST crash window / read-committed 语义未定义

来源：rev-claude-architect A1。  
状态：架构方向孤点，但 Critical。  
处理：specs/01 必须明确 BROADCAST 只在 `commit().await == Ok` 后开始；engine crash 于 commit 与 broadcast 之间时如何通过 `/tick/{N}/complete`、keyframe 或 correction delta 恢复。

### A-H2: Core IDL 与 World Action Manifest 边界需拆层

来源：rev-gpt-architect A4、rev-claude-architect A3、rev-dsv4-architect 三层扩展确认。  
处理：Core IDL 仅定义基础 envelope/ABI/host functions；World Action Manifest 定义 world.toml/Rhai/custom action，并带 canonical hash、版本、TickTrace 绑定、WASM target_manifest_hash。

### A-H3: 规模拐点与事务模型需写入 ADR / acceptance gate

来源：rev-claude-architect A4/A6，rev-gpt-architect A6，rev-dsv4-architect N4/N5。  
处理：P0 允许 500-player MVP；P1 必须有 1000-player stress gate；3000/5000 玩家触发 per-room transaction / sharding ADR。

### S-H1: RespawnPolicy residual 需核验

来源：rev-dsv4-security CRITICAL-1。  
处理：grep R2 所指的 `Spectate|Ban` as RespawnPolicy；若仍存在，统一为最终枚举。因只有 1/9 直接报告，Speaker 不把它列为共识 Blocker，但它是低成本高风险的 immediate fix。

### S-H2: RuleMod supply chain 与 Rhai action apply limits

来源：rev-gpt-security H-5，rev-claude-security HIGH-4。  
处理：mods.lock checksum/signature 必需；capability manifest 最小授权；Rhai actions per-target/per-tick limits；多模组 apply 顺序 deterministic，不递归。

### D-H1: First Hour / Progressive Reveal / AI Curriculum 是 Designer 方向首要通过条件

来源：rev-gpt-designer G1-G4，rev-claude-designer Missing M1-M4，rev-dsv4-designer G5。  
处理：新增或补齐 first-hour journey、progressive reveal ruleset、AI-readable curriculum、Novice Vanilla 分层。核心实现可继续，但第一个可玩里程碑不能只交付完整系统的缩水版。

### D-H2: Fortify / Special Attack balance matrix 需要决策

来源：rev-dsv4-designer G2，rev-claude-designer G3，rev-gpt-designer G4。  
处理：完成 special attack pairwise counterplay 审计；明确 Fortify 是否同时护盾+净化，Overload fuel reduction 是否可被净化；考虑 Fortify/Purge 拆分或净化成本。

### D-H3: World PvE→PvP 激励梯度与 Arena 产品闭环仍缺

来源：rev-dsv4-designer G1/G6，rev-gpt-designer G5/G7，rev-claude-designer M3/M4。  
处理：World 至少定义 Novice/Standard/Hardcore conflict presets；Arena 至少定义 quick match + replay + basic rating，否则降级为 experimental。

---

## Medium / Low 处置

| ID | 问题 | 负责 Phase | 处置 |
|---|---|---:|---|
| M1 | f64 / TOML float residual | Spec convergence | validate_config 拒绝 float literal，示例改 fixed-point integer |
| M2 | seed_rotation_interval 上下限 | Spec convergence / Phase 1 | 增加 `[100, 100000]` 或等价范围与 domain separation |
| M3 | path_find terrain secrecy 模型 | Phase 1 | 明确 terrain 公开是规则还是 unexplored terrain 受 fog 限制 |
| M4 | Rejection detail / prompt injection / UI escaping | Phase 1 | untrusted annotations + prompt delimiter + Web UI escape |
| M5 | Replay share card / highlights / weekly digest | Public beta | Designer backlog，非实现冻结 blocker |
| M6 | Colony Chronicle / Bot Lineage / identity | Public beta | 预留数据模型；完整产品可后置 |
| M7 | Recon / counter-recon / decaying intel | Phase 2+ | 设计深度增强项，不阻塞 P0 |
| M8 | Broadcast fan-out / spectator sample rate | Phase 4 | 压测后确定降级策略与压缩方案 |
| M9 | Emergency Wasmtime playbook | Pre-production | 安全运维文档；生产前必须有 |
| M10 | Admin rollback dual-control semantics | Pre-production | 签名 payload、不同人/不同 key、anti-replay 明确化 |

---

## 文档维护项

1. 在 R2 convergence patch 后更新：
   - `/data/swarm/docs/reviews/R2/R2-SPEAKER-VERDICT.md` 本报告状态；
   - `docs/reviews/README.md` 的 R2 verdict；
   - `ROADMAP.md` 中所有 ✅ 与 pending 项，避免 green dashboard theater。
2. 建议新增或拆分文档：
   - `docs/design/first-hour-journey.md`
   - `docs/design/progressive-reveal-ruleset.md`
   - `docs/design/ai-curriculum-resources.md`
   - `docs/design/arena-product-spec.md`
   - `docs/design/special-attack-balance-matrix.md`
   - `docs/design/world-conflict-escalation.md`
   - `docs/design/failure-recovery-loop.md`
   - `docs/security/wasm-deploy-signature.md` 或在 specs/03/specs/09 中合并完成
   - `docs/adr/world-action-manifest-and-replay-hash.md`
3. 删除/内部化所有不应公开暴露的 `TargetFuelTooLow`、旧 RespawnPolicy、六边形 Direction、危险 `spectate_delay=0` 示例。
4. 添加 consistency CI 或文档检查脚本，避免 R3 再次出现 DESIGN 已改而 specs/IDL 未改。

---

## R3 / 下一轮入场条件

进入 R3 前，建议至少完成以下 gate：

1. B1 Overload 全链路闭合：specs/02、specs/08、api/commands、TickTrace/replay、Fortify/fuel recovery 语义一致。
2. B2 Spec Convergence Patch：Direction、Tick schedule、Command limits、spectate_delay、IDL/Manifest 边界统一。
3. B3 Tick mutation semantics：Phase 2a TOCTOU 合同 + Phase 2b canonical schedule / RW matrix。
4. B4 部署签名：nonce/CRL/epoch/cache invalidation 或明确改用 bearer/mTLS 模型。
5. B5 输出面：MCP transport browser/agent 拆分 + DNS rebinding tests + spectator delay validation。
6. B6 资源边界：snapshot cap、simulate cap、audit cap。
7. Designer 最小补强：First Hour + Novice Vanilla + AI curriculum skeleton + Arena 是否 experimental 的明确决策。

---

## 用户裁决（2026-06-16）

1. **MVP Phase 2b**：✅ 保留并行，但须先给出 Component/Resource 读写矩阵证明无冲突。

2. **Overload fuel reduction**：✅ 短期压制（方案 A）。fuel 减少为临时 debuff，可被 Fortify/Purge 清除，有自然恢复曲线（建议 `tick/10`）。需在 spec 中明确恢复曲线 + Fortify 交互 + 全局冷却 key。

3. **部署认证模型**：✅ 客户端 Ed25519 签名。需补 nonce/timestamp/world_id/player_id/module_slot/version_tag/CRL/epoch。

4. **Vanilla 首发复杂度**：✅ 分层关闭。首发默认 Tutorial/Novice，特殊攻击（Hack/Overload/Fortify 等）默认禁用，通过 progressive reveal 逐步解锁。

5. **Arena 产品定位**：✅ Experimental。未达 quick match/basic rating/replay product 前不宣称 MVP 主入口。

---

## 最终结论

R2 不是架构失败轮，而是“设计方向正确、实现合同未收敛”的典型收敛轮。Speaker 建议：不要重写大设计；做一次集中 convergence patch。修完 B1-B6 后，R3 应聚焦验证这些合同是否真正同步，而不是重新讨论核心架构。

当前裁决保持：**REQUEST_MAJOR_CHANGES**。完成 R3 入场条件后，预计可升级为 **APPROVE_WITH_RESERVATIONS**；若 R3 九评审确认无新的 Critical/Blocker，可进入实现冻结。
