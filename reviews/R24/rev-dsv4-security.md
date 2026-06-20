# R24 Security Review — rev-dsv4-security

**Reviewer**: rev-dsv4-security (DeepSeek V4 Pro)
**Direction**: Security — 协议一致性验证、数据流追踪、竞态条件检测
**Review Type**: Clean Slate — spec ↔ design 全量对齐检查
**Documents Reviewed**: design/ (README, auth, engine, gameplay, modes, interface, tech-choices) + specs/ (core/01-05, security/03/05/09, gateway-protocol, reference/api-registry) — 共 15 份核心文档

---

## Verdict: CONDITIONAL_APPROVE

发现 **2 Critical**（同文档内部矛盾）、**6 High**（跨文档不一致/安全GAP）、**3 Medium**、**2 Low**。Critical 项必须在合并前修正（内部矛盾直接影响实现选择）；High 项应在下一个设计迭代中解决。无安全架构层面的根本性缺陷——协议隔离（Source Gate、证书链、WASM 沙箱）设计正确，问题集中在数值/分类/命名的一致性上。

---

## Critical

### C1 — CSR Replay Class 内部矛盾
**位置**: design/auth.md §5.6a 第 319 行 vs §5.6b 第 344 行

**冲突描述**:
- §5.6a（Replay Class 分类表）将 `swarm_submit_csr` 列为 `idempotent_mutation`，标注 nonce 策略为 "Dragonfly nonce + time window（除 deploy 外）"
- §5.6b（授权矩阵）将同一个 `swarm_submit_csr` 列为 `non_idempotent_mutation`

**影响**: 两种 Replay Class 使用完全不同的防重放机制：
- `idempotent_mutation` → Dragonfly SETNX TTL（300s 窗口，崩溃后可重放）
- `non_idempotent_mutation` → FDB 事务内原子消费 challenge（严格一次性，崩溃后不重放）

§10.8 的 Nonce vs Version Counter 表和 §9.3 的服务端验证流程均描述 PoW challenge 在 FDB 事务内原子消费——与 `non_idempotent_mutation` 一致。**结论**: §5.6a 的分类是错误，应修正为 `non_idempotent_mutation`。

**修正建议**: 将 §5.6a 表中 `swarm_submit_csr` 的 Replay Class 从 `idempotent_mutation` 改为 `non_idempotent_mutation`，nonce 策略改为 "FDB 事务内消费 challenge（一次性）"。

---

### C2 — CodeSigningCertificate TTL 数值内部冲突
**位置**: design/auth.md §5.3 (L274) vs §5.5 (L296) vs §14.1 (L1218)

**冲突描述**:
| 位置 | CodeSigningCertificate TTL |
|------|--------------------------|
| §5.3 用途隔离证书表 | **7d**（固定值） |
| §5.5 多设备证书生命周期表 | **30–180 days**（常用设备） |
| §14.1 Token 生命周期表 | **15 min–180 days** |

三个不同位置给出三个不同的 TTL 范围。7d 对安全有利（缩短吊销窗口），30-180 days 对 UX 有利（减少续签频率）。没有明确哪个是权威值。

**影响**: CodeSigningCertificate 的 TTL 直接影响：(1) 部署时证书过期检查窗口；(2) CRL 保留窗口计算（`max_certificate_ttl` 项）；(3) 玩家续签频率和凭据管理 UX。specs/security/09-command-source.md §3.4 引用 design 的 30-180 days，api-registry.md 未声明 TTL——说明 spec 已默认采纳较长 TTL，与 §5.3 的 7d 冲突。

**修正建议**: 以 §5.5 和 §14.1 的 `30–180 days` 为准（与设备类型模型一致），修正 §5.3 表格中 CodeSigningCertificate 的 TTL 为 `30–180 days`（或添加注释说明 7d 为默认推荐值但可配置延长）。

---

## High

### H1 — 快照截断优先级桶序不一致
**位置**: design/engine.md §3.4.4 (L422) vs specs/core/01-tick-protocol.md §2.3 (L156-160)

**冲突描述**:
- design §3.4.4: 优先级桶序 = `自机 > 友方 drone > 敌方 drone > 建筑 > NPC > 资源`
- spec §2.3: 分 4 个 bucket，建筑分散到关键桶（Spawn/Controller/depot 无条件保留）和高优先桶（己方建筑），且桶内排序键不同

design 将"建筑"作为统一桶排在敌方 drone 之后，而 spec 将关键建筑提升到无条件保留的关键桶——这意味着 Spawn/Controller/depot 在 spec 中永远不会被截断，但在 design 中可能在资源不足时被丢弃。

**影响**: 截断顺序影响 WASM tick() 输入的信息集，进而影响回放确定性。如果实现按 spec 的 4 桶模型编码但 QA 按 design 的 6 类模型测试，会产生验收偏差。

**修正建议**: design/engine.md §3.4.4 的优先级描述应更新为与 specs/core/01-tick-protocol.md §2.3 一致（spec 为权威）。添加从 design 到 spec 的显式引用指针。

---

### H2 — WASM Worker 1000-tick 强制替换缺失于 sandbox spec
**位置**: design/engine.md §3.4.3 (L409) → specs/core/04-wasm-sandbox.md GAP

**冲突描述**:
- design/engine.md §3.4.3 明确规定："每 worker 最多服务 1000 tick 后强制替换；OOM/trap/timeout 后立即替换并记入 audit log"
- specs/core/04-wasm-sandbox.md §1 描述 "long-lived worker pool + per-tick clean Store/Instance reset"，仅说明 Store reset 清空 WASM 可变状态，**未提及 worker 生命周期上限**

**影响**: Worker 强制替换机制防止跨 tick 累积的状态泄露（如 Wasmtime 内部缓存、JIT 代码残留、内存碎片攻击）。per-tick Store reset 不能替代 worker 替换——OS 级资源（文件描述符、内存映射、cgroup 计数器）在 Store reset 中不清零。此安全措施在实现 spec 中缺失可能导致实现遗漏。

**修正建议**: 在 specs/core/04-wasm-sandbox.md §1 末尾添加 worker 生命周期约束段落，明确 1000-tick 上限、OOM/trap/timeout 后立即替换、替换审计日志。

---

### H3 — Arena 独立预算在 tick protocol spec 中缺失
**位置**: design/engine.md §3.4.1 (L291) → specs/core/01-tick-protocol.md GAP

**冲突描述**:
- design/engine.md §3.4.1 为 Arena 定义独立预算：tick interval 300ms, COLLECT 200ms, EXECUTE 50ms, COMMIT 20ms, BROADCAST 10ms
- specs/core/01-tick-protocol.md §2.2 仅包含 World 模式超时值：collect_timeout_ms = 2500

Arena 的短周期预算约束（300ms tick vs World 的 3000ms）在核心 tick 协议 spec 中完全未体现。实现者仅阅读 spec 会默认采用 2500ms 超时，导致 Arena 模式下的 tick 超时保护失效。

**修正建议**: 在 specs/core/01-tick-protocol.md §2.2 添加 Arena 模式的超时配置，或添加明确引用指向 design/engine.md §3.4.1 和 design/modes.md §9.1.2。

---

### H4 — Refresh Token Grace 窗口并发语义未指定
**位置**: design/auth.md §14.1 (L1223-1228)

**描述**:
```
旧 token 在 rotation 后 60s 内仍可被接受一次（grace period，防竞态）
grace 使用必须原子消费：FDB 中设置 grace_consumed_at，避免重复使用
```

设计声明 grace_consumed_at 需原子消费，但未指定：
1. 并发原子操作机制（FDB 事务内 CAS？versionstamp？）
2. 两个客户端同时使用旧 token 时的语义（都成功？仅一个成功？）
3. grace 被消费后新 token 是否立即可用

**影响**: 在分布式部署中（多个 Gateway 实例），两个客户端可能同时提交相同的旧 refresh_token。若未正确实现原子 grace_consumed_at，可能导致双倍 refresh token 签发，形成 session fixation 攻击面。

specs/security/03-mcp-security.md 和 specs/gateway-protocol.md 均未覆盖 refresh token rotation 的并发语义。

**修正建议**: 在 design/auth.md §14.1 中补充：
1. grace_consumed_at 的 FDB 事务实现（versionstamp CAS 或原子 read-check-write）
2. 并发消费语义：仅第一个成功，后续返回 `RefreshTokenInvalid`
3. 补充并发测试用例：`test_refresh_token_grace_concurrent_rejects_second`

---

### H5 — 联邦 CRL 同步超时后信任边界模糊
**位置**: design/auth.md §15.2a (L1336-1338) vs §15.6 (L1389-1395)

**冲突描述**:
- §15.2a 定义 `revocation_fallback` 三级策略：`reject_for_code` / `reject_all` / `allow_with_warning`
- §15.6 定义 `revocation_fallback` 三级策略：`reject_for_code` / `accept_login` / `reject_all`

两个位置对 fallback 策略的枚举不同：§15.2a 有 `allow_with_warning`，§15.6 有 `accept_login`。这两个语义是否等价不明确。

此外，§15.6 的 stale 超时 `revocation_cache_stale_seconds`（默认 3600s）与 §15.2a 的同步间隔 60s 之间的数学关系：若同步间隔 60s 且 `revocation_fallback` 的 `reject_for_code` 触发条件是 "CRL 超过 2× 同步间隔未更新"（120s），但 stale 超时为 3600s——意味着在 120s 到 3600s 之间 login 仍被允许但 code signing 被拒绝。此行为与 §15.6 的 `accept_login` 策略一致，但两处的参数化和命名不同。

**修正建议**: 统一 §15.2a 和 §15.6 的 fallback 策略枚举。以 §15.2a 为准（`reject_for_code` / `reject_all` / `allow_with_warning`），将 §15.6 的 `accept_login` 改为 `allow_with_warning` 并添加明确注释。

---

### H6 — Admin 双签要求跨文档粒度不一致
**位置**: design/auth.md §10.5b (L800-808) vs design/auth.md §11.3 (L1061)

**冲突描述**:
- §10.5b "Admin 高权限操作认证" 表：Epoch bump / force CRL rotation 需要 "AdminCertificate 签名 + 第二个 Admin 确认"，但 Batch revoke 仅需 "AdminCertificate 签名"（无双签）
- §11.3 "管理员生成恢复链接"：`swarm_admin_create_password_reset` 要求 "双人授权——需要两个不同 admin 的确认"

两个位置对"哪些操作需要双签"的划分不一致。§10.5b 说恢复链接生成仅需单 AdminCertificate 签名，§11.3 说需要双人授权。此外，specs/reference/api-registry.md §3.2 Admin tools 表中未对任何 admin 工具标注双签要求。

**修正建议**: 统一双签策略。建议以 §11.3 为准（恢复链接 = 双签，因为是高敏感操作），并更新 §10.5b 表和 api-registry.md 中的 admin 工具标注。

---

## Medium

### M1 — Audience 字段模板命名不一致
**位置**: design/auth.md §10.8 (L882) vs specs/gateway-protocol.md §8 (L150)

design 使用模板 `swarm-aud-v1:<transport>:<server_id>:<world_id>:<subject_id>`（通用命名——"对于玩家操作为 player_id，对于服务间调用为 server_id"）。gateway spec 使用 `transport:server_id:world_id:player_id`（直接命名）。

语义等价但命名不一致——实现者可能混淆 subject_id 和 player_id 是否互換。

**修正建议**: 统一使用 `swarm-aud-v1:<transport>:<server_id>:<world_id>:<subject_id>`（design 版本更通用），gateway spec 更新匹配。

---

### M2 — Auth MCP 工具 scope 粒度不一致
**位置**: design/auth.md §5.6b (L345) vs specs/reference/api-registry.md §3.2 Admin (L301-309)

design §5.6b 中 `swarm_admin_create_password_reset` 的 scope 为 `swarm:admin:recovery`（细粒度），但 api-registry.md 中所有 Admin 工具统一使用 `swarm:admin`（粗粒度）。

scope 粒度影响权限模型：细粒度允许拆分管理权限（如恢复管理员 vs 配置管理员），粗粒度统一授权。当前混合状态（部分文档细粒度、部分粗粒度）会导致实现歧义。

**修正建议**: 决定一种策略并统一。若选择细粒度，需在 api-registry.md 中拆分 admin scope。若选择粗粒度（当前实现路径更简单），design §5.6b 表中删除 `:recovery` 后缀。

---

### M3 — Overload 受害者信息不对称（有意设计，需文档化）
**位置**: specs/security/05-visibility.md §6.1 (L226-241)

Overload 攻击者无法区分"目标不存在"与"目标不可见"（返回统一码 `NotVisibleOrNotFound`）——正确防 oracle。但目标玩家可通过自身 fuel 变化感知被攻击，且 `OverloadPressure.total` 对目标可见（包括来自不可见攻击者的累积压力）。

这形成了有意的不对称——攻击者被剥夺目标信息，但目标可感知总压力。设计意图正确（目标有权知道自身 fuel 下降），但应文档化威胁：目标可通过观察 `OverloadPressure.total` 的变化率推断攻击者数量，即使攻击者不可见。此推断精度受限于 total 值的粒度。

**修正建议**: 在 specs/security/05-visibility.md §6.1 target 视角中补充："target 可通过 total 变化率间接推断攻击者数量下限，此信息泄露在当前设计中接受（精度有限，且不影响攻击者身份暴露）"

---

## Low

### L1 — PoW 难度配置分散在三处
design/auth.md §9.2（默认 24）、§9.4（recovery PoW 默认关闭）、附录 C world.toml（`register_pow_difficulty_bits = 24`）。信息一致但分散——实现者可能错过某处导致默认值不一致。

**修正建议**: 将 PoW 难度默认值收敛到一处（建议 §9.2），其他位置引用。

### L2 — Worker pool size 描述中 cgroup pids.max 不一致
design/engine.md §3.4.3 提到 cgroup pids.max 限制，但 specs/core/04-wasm-sandbox.md §4.2 表中 pids.max = 32，而 §9.1 OS 加固表中 pids.max = 16。

**位置**: specs/core/04-wasm-sandbox.md §4.2 (L261) vs §9.1 (L387)

16 vs 32 的差异——16 对于多线程 WASM 编译可能不足。

**修正建议**: 统一为 32（与 §4.2 主配置区一致），更新 §9.1 OS 加固表。

---

## Cross-Check Items for Other Reviewers

以下是与安全域交叉但更适合其他方向裁决的发现，提交 cross-check：

| # | 发现 | 建议方向 |
|---|------|---------|
| X1 | `swarm_simulate` 的 rate limit：specs/security/03-mcp-security.md §5.1 说 "5/tick"，api-registry.md §3.2 Debug 说 "50/tick"。两者相差 10 倍。 | **API/DX** |
| X2 | Pathfinding budget：design/engine.md §3.4.2 说 per-player 10 calls + 100,000 explored nodes/tick 全局，api-registry.md §4.2 确认 10 calls/tick，但 api-registry.md §5.2 说 "Pathfinding budget 100,000 explored nodes/tick"。无 per-player fair-share 分配在 registry 中的明确声明。 | **Performance** |
| X3 | drone lifespan 默认值：design/engine.md §3.1 定义 1500 tick 默认值，但 design/gameplay.md §2 的 Drone 生命周期表使用相同值。api-registry.md §5.1 确认 1500 ticks。一致，但 gameplay.md 提到 `MIN_LIFESPAN` 默认 100 tick——此参数不在 api-registry 容量限制表中。 | **Architect** |

---

## Review Statistics

| Metric | Value |
|--------|-------|
| Documents reviewed | 15 (7 design + 8 spec) |
| Total lines scanned | ~12,000+ |
| Critical findings | 2 |
| High findings | 6 |
| Medium findings | 3 |
| Low findings | 2 |
| Cross-check items | 3 |
| Architecture-level concerns | 0 |

---

## Data Flow Integrity (安全特有评估)

对安全评审特有视角的额外检查：

### Tick 协议并发一致性

| 检查项 | 状态 | 依据 |
|--------|:----:|------|
| 超时玩家影响范围 | ✅ 隔离 | 01-tick-protocol §2.2: 超时 → commands[player] = []，不阻塞世界 |
| 指令队列不跨 tick | ✅ 正确 | 01-tick-protocol §3.3: "超时玩家的指令输出仅丢弃当前 tick" |
| Snapshot 构建时序 | ✅ 正确 | 01-tick-protocol §2.3: COLLECT 开始时一次性构建，WASM tick 与 MCP query 同一份快照 |
| FDB commit 失败恢复 | ✅ 正确 | 01-tick-protocol §3.5: Bevy World 快照恢复 + COLLECT 结果缓存复用 |

### 数据流信任链

| 阶段 | 上游 | 下游 | 校验 |
|------|------|------|:----:|
| CommandIntent → RawCommand | WASM 输出 | Source Gate | ✅ player_id/source/tick 服务端注入 |
| RawCommand → ValidatedCommand | Source Gate | 预校验 | ✅ 静态检查（所有权/距离/资源） |
| ValidatedCommand → Apply | 预校验 | ECS World | ✅ inline 逐条校验基于当前 Bevy World |
| Apply → FDB commit | ECS World | FDB | ✅ 原子提交，失败回滚 |

无"信任下游会校验"的假设——每阶段独立校验。

### 路径依赖安全

| 检查项 | 状态 |
|--------|:----:|
| 是否存在 Admin 专用绕过路径 | ✅ 无 — 09-command-source §2.3: Admin 走标准 validate_and_apply() |
| WASM 能否直接调用 mutating host function | ✅ 否 — 04-wasm-sandbox §3.3 明确禁止 |
| MCP 能否提交 gameplay 指令 | ✅ 否 — 09-command-source §4: Source Gate 拒绝 |
| 旁观者能否通过 WebSocket 提交指令 | ✅ 否 — gateway-protocol: spectator WS 只读 |

### 算法边界安全

| 检查项 | 设计上限 | 硬截止 |
|--------|---------|:------:|
| Pathfinding 最大计算量 | 100,000 explored nodes/tick + 10 calls/player | ✅ 超限 deterministic fail |
| 恶意构造超大地图 | 50×50 格/房间, world_size 限制房间数 | ✅ 引擎配置约束 |
| WASM tick 输出体积 | 256KB JSON | ✅ 超限拒绝整 tick 输出 |

---

*Review completed 2026-06-20. 下一轮 Closure Verification 建议重点关注 C1 (CSR Replay Class) 和 C2 (CodeSigningCertificate TTL) 的修正确认。*