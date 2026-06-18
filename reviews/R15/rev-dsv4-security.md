# R15 Security Review — DeepSeek V4 Pro

> **评审范围**: Phase 1 Clean-Slate，仅限安全方向指定文档子集。
> **评审原则**: 设计阶段评审，不考虑分阶段实现。有合适方案直接采纳，不考虑实现难度。

---

## 1. Verdict

**CONDITIONAL_APPROVE** — 设计整体安全架构扎实：应用层证书模型设计严谨、deferred command 模型隔离良好、可见性策略有 oracle 防御意识、WASM 沙箱 OS 层加固全面。但存在 **2 个 Critical**（spec 内部矛盾 + Intermediate CA 私钥保护不足）和 **3 个 High**（CRL 默认延迟过长、host function 无限调用、Dragonfly 崩溃下的重放窗口），需在进入实现前解决。

---

## 2. 发现的问题

### Critical

#### C1 — Deploy 防重放机制 spec 内矛盾 (auth.md §5.6a vs §10.8)

**位置**: `design/auth.md` 第 312-318 行 vs 第 850-872 行

§5.6a 将 `swarm_deploy` 归类为 `idempotent_mutation`，指定其 nonce 策略为 "Dragonfly nonce + time window"。但 §10.8 明确写道 "Deploy 不使用 nonce——防重放由 version_counter 保证"，并在 §7.3 详细描述了基于 FDB 持久化 `version_counter` 的防重放机制。

两条路径的安全属性完全不同：
- Dragonfly nonce（§5.6a）：Dragonfly 崩溃后 nonce 全丢，TTL 窗口内的已部署 nonce 可被重放
- FDB version_counter（§10.8）：严格递增，崩溃后不重放，持久化保证

**建议**: 统一使用 FDB version_counter 方案（§10.8 的方案），从 §5.6a 的 replay class 表中移除 `swarm_deploy` 的 Dragonfly nonce 引用，或明确标注 `swarm_deploy` 为特殊处理（不在 Dragonfly nonce 覆盖范围内）。同时 `idempotent_mutation` 类别下若还有其他方法，需逐一确认其 nonce 存储选择。

#### C2 — Server Intermediate CA 私钥在线暴露风险 (auth.md §3.1, §3, §17.1)

**位置**: `design/auth.md` 第 106-131 行，第 124-129 行

Auth Service 需要在线签发证书，因此必须持有 Server Intermediate CA 私钥。设计文档对生产环境推荐 HSM，但：

1. **自托管/小型部署**（soft-HSM / pkcs11-tool / 文件系统 0600）：Auth Service 是网络可达的服务进程，直接持有 Intermediate CA 私钥。一旦 Auth Service 被攻破（如 RCE via MCP 参数解析漏洞、内存损坏），攻击者获得 Intermediate CA 私钥 = 可签发任意玩家的 `ClientAuthCertificate` 和 `CodeSigningCertificate`，绕过整个认证体系。

2. **Intermediate CA 轮换周期 90 天**过长：若私钥泄露未被发现，攻击者有至多 90 天的窗口签发伪造证书。Epoch emergency bump 可全局失效，但这要求运维**先发现泄露**。

3. **威胁模型遗漏** (§17.1)：当前威胁模型列出了 18 项威胁和缓解措施，但**未包含 "Auth Service 进程被攻破 → Intermediate CA 私钥泄露"** 这一威胁。这是整个认证体系的单点故障。

**建议**:
- 威胁模型增补：Auth Service RCE → Intermediate CA 私钥泄露，缓解措施包括 HSM 强制、进程沙箱（seccomp/cgroup 与 sandbox worker 同级）、最小权限运行
- 自托管部署的 Intermediate CA 私钥保护从 "0600 文件" 升级为强制 soft-HSM（如 SoftHSM2 + pkcs11），拒绝纯文件系统方案
- CA 私钥操作日志独立于 Auth Service 日志（append-only, 不可删除），记录每次签名操作的证书指纹 + 时间戳
- Intermediate CA 轮换周期从 90 天缩短至 30 天（若 HSM 不可用）或保留 90 天（仅 HSM 场景）

---

### High

#### H1 — CRL 吊销延迟默认 60s 对竞技环境过长 (auth.md §10.8)

**位置**: `design/auth.md` 第 896-901 行

证书吊销状态 (CRL) 缓存允许 60s 延迟，并明确标注 "明确接受的风险：吊销后至多 60s 旧证书仍可被接受"。文档提到 "竞争性世界可配置为 5-10s"，但：

1. 默认值是 60s，这意味着粗心或不知情的部署者将使用 60s 窗口
2. 60s 在 MMO RTS 场景中可覆盖多个 tick（若 tick=3s，即 20 tick），攻击者可用刚被吊销的证书在窗口内执行破坏性操作
3. 没有 `validate_config` 层面的强制约束：竞技世界不强制要求 CRL 缓存 ≤ 10s

**建议**: 
- 将默认 CRL 缓存 TTL 降至 10s（全局默认）
- `world.toml` 的 `validate_config` 逻辑中：若 `competitive = true`（或 Arena 模式），强制 `crl_cache_ttl ≤ 10s`
- 文档中将 "明确接受的风险" 改为 "可配置的风险窗口"，并注明竞技部署必须收紧

#### H2 — Sandbox Worker 池化模型下的跨 Tick 状态残留风险 (specs/core/04-wasm-sandbox.md §1)

**位置**: `specs/core/04-wasm-sandbox.md` 第 41-43 行

Sandbox 采用 **long-lived worker pool** 模型。每个 tick 执行 "Store reset"：清空线性内存、重置 fuel counter、重建 Instance。但：

1. Wasmtime `Store` reset 是否保证**所有内部状态**清零？包括：Wasmtime 内部的 epoch deadline、StoreLimits、signal handler 状态等
2. Wasmtime 的 Cranelift JIT 编译产物缓存在 Engine 层（跨 Store 共享）——若 JIT 代码缓存存在 bug，一个玩家的恶意 WASM 可能影响后续使用同一 Engine 的其他玩家
3. 当前文档没有描述 **Store reset 的原子性验证**——如果 reset 中途失败（如 OOM），worker 是回到池中还是销毁重建？

**建议**:
- 明确定义 Store reset 的验证清单：reset 后检查 fuel=10M、memory=0、epoch deadline 重置
- Worker 池增加 health check：每 N tick 或每次异常后，对 worker 执行空 tick 验证
- 若 Store reset 过程中任何步骤失败 → worker 进程终止并重建，不回池
- CI 增加 "跨 tick 状态残留" 测试：部署恶意 WASM 执行后，同 worker 下一 tick 执行合法 WASM，断言无状态泄露

#### H3 — `host_get_terrain` / `host_get_world_config` / `host_get_world_rules` 无 per-tick 调用上限 (specs/core/04-wasm-sandbox.md §8)

**位置**: `specs/core/04-wasm-sandbox.md` 第 347-358 行

`host_get_objects_in_range` 限制 5/tick，`host_path_find` 限制 10/tick。但 `host_get_terrain`（500 fuel/次）、`host_get_world_config`（1000 fuel/次）、`host_get_world_rules`（1000 fuel/次）没有 per-tick 调用次数上限。

`host_get_terrain` 单次仅 500 fuel，10M fuel 预算下可调用 20,000 次。虽然没有直接的信息泄露（terrain 是公开信息，但调用模式可能泄露玩家策略意图），但这构成一个 DoS 向量：恶意 WASM 可消耗全部 fuel 在无意义的 terrain 查询上，同时通过大量 host function 调用增加引擎侧 CPU 开销（每次调用涉及跨进程 gRPC + JSON 序列化）。

**建议**:
- `host_get_terrain` 增加 per-tick 上限 100 次（远超合理游戏需求）
- `host_get_world_config` 和 `host_get_world_rules` 增加上限 5/tick（这些数据在 tick 内不变，缓存即可）
- 或者在 fuel 成本中计入 host function 调用的固定 overhead（如每次调用 +5000 fuel 基础成本），使恶意高频调用自然耗尽 fuel

---

### Medium

#### M1 — Dragonfly 崩溃下的 Nonce 重放窗口 (auth.md §10.8)

**位置**: `design/auth.md` 第 839-848 行

MCP 查询请求的 nonce 存储在 Dragonfly（Redis-compatible），TTL 300s。Dragonfly 崩溃后：
- 所有未过期 nonce 丢失
- 崩溃 + 重启后的 300s 窗口内，之前使用过的 nonce 可被重放
- 重放仅影响 `read_replay_safe` 操作（读操作），所以实际安全影响低
- 但如果 Dragonfly 崩溃与网络分区同时发生，攻击者可在窗口内重放读请求获取一致的世界快照

**建议**: 文档中明确标注 Dragonfly nonce 的崩溃语义为 "TTL 窗口内可重放"，设计上接受此风险。对高安全部署，提供 FDB-based nonce 选项（使用 FDB TTL 事务）。

#### M2 — SSE `Last-Event-ID` 验证机制未详述 (specs/security/03-mcp-security.md §2.3)

**位置**: `specs/security/03-mcp-security.md` 第 128 行

SSE 重连防御提到 "SSE Last-Event-ID 验证 + token per-session binding"，但未详述：
1. `Last-Event-ID` 的格式和签名机制
2. 如何防止攻击者猜测或枚举有效 ID
3. 重连时的 token 验证流程

**建议**: 补充 `Last-Event-ID` 的安全设计：ID 应为 `HMAC(session_token, event_sequence)` 或类似不可伪造结构，使攻击者无法构造有效 ID 劫持 SSE 流。

#### M3 — Snapshot `truncated` + `omitted_count` 分桶后仍有残余 oracle (specs/security/05-visibility.md §10.2)

**位置**: `specs/security/05-visibility.md` 第 378-392 行

`omitted_count` 分桶方案（few/some/many/extreme）比精确数字好，但：
- 攻击者可通过多次请求观察分桶值变化推断实体数量范围
- 例如：连续两 tick 的 `omitted_count` 从 "few" 变为 "some"，暗示 ~10 个新实体出现
- 在 competitive 模式下，这种粗粒度信息仍可能有用

**建议**: 在 competitive 模式下，`omitted_count` 仅返回布尔 `truncated: true/false`，不分桶。non-competitive 模式保留分桶用于调试。或者将分桶边界随机化（每 tick 随机偏移 ±20%）以增加推断难度。

#### M4 — 账号删除时 in-transit 资源处置依赖引擎侧实现 (auth.md §13.1)

**位置**: `design/auth.md` 第 1136-1141 行

账号删除步骤 4 要求同一 tick 内原子处理 cargo transfer 取消、market order 回滚、depot transaction 回滚。但 Auth Service 是独立进程，Engine 是独立进程，两者间没有描述事务协调机制。若 Auth Service 标记 `deleted_at` 后 Engine 处理资源处置时失败（如 tick 超时），可能出现 "账号已标记删除但资源未回滚" 的半状态。

**建议**: 
- 账号删除使用两阶段协议：Phase 1 (Auth) 标记 `deletion_pending` → Phase 2 (Engine) 在下 tick 执行资源处置并标记 `deletion_committed`
- 或通过 FDB 事务跨 Auth/Engine subspace 原子操作（两者使用同一 FDB 集群时可行）
- 明确半状态的恢复流程

#### M5 — `host_path_find` 不可达目标消耗更高 (specs/core/04-wasm-sandbox.md §8)

**位置**: `specs/core/04-wasm-sandbox.md` 第 355 行

文档注明 "不可达目标消耗更高（无路径可剪枝）"。这意味着攻击者可通过指定不可达目标（如地图外的坐标、被障碍物完全包围的点）放大 pathfinding 计算成本。加上 `host_path_find` 的 cache miss penalty，恶意构造的请求可消耗大量引擎 CPU。

当前 mitigations：10 次调用/tick 上限 + 100,000 explored_nodes 总额度。这些限制是合理的。但 explored_nodes 计数是事后统计——如果单个 path_find 调用就超出 100,000 nodes，是在调用中途终止还是在调用完成后拒绝？

**建议**: 明确 path_find 的超限处理：若单次调用在达到 explored_nodes 上限前未找到路径 → 立即终止并返回 `PATH_NOT_FOUND`（不等待完整搜索完成）；若累计超出 100,000 → 后续 path_find 调用返回 `PATH_QUOTA_EXCEEDED`。

---

### Low

#### L1 — Auth Service argon2id 并发限流建议值偏低 (auth.md §6.1)

**位置**: `design/auth.md` 第 477 行

建议 semaphore 限制为 `min(cpu_cores, 4)`。对于现代服务器（64+ cores），4 并发可能过于保守，正常用户的密码验证会排队。但对于安全侧，这个保守值在防止 DoS 放大方面是正确的。建议在文档中注明这是 "安全侧建议"，运维可按实际负载调整（不大于 cpu_cores/4）。

#### L2 — `username_visibility` 默认 `private` 是正确选择 (auth.md §7.2)

好的设计：默认 `private` 模式防止用户名枚举。确认此设计的正确性。

#### L3 — `temporary_device` / `managed_device` 约束完善 (auth.md §5.2)

临时设备和托管设备的权限约束（不可签发 admin、不可为其他设备续签、不可吊销其他设备证书）设计周全。确认。

#### L4 — 证书生命周期 UX 通知渠道完善 (auth.md §10.9)

MCP 响应头 `Swarm-Cert-Expires-In` + SSE 事件 `certificate_expiring_soon` 设计良好。确认。

---

## 3. 亮点

1. **Deferred Command Model 隔离优秀** (04-wasm-sandbox.md §3): WASM 不能直接调用 mutating host function，所有游戏动作通过 `tick() → JSON` 延迟模型提交。这是沙箱安全的基石设计。

2. **应用层证书 + CSR 模型设计严谨** (auth.md §5): Server CA 离线、用途隔离证书（ClientAuth/CodeSigning/Admin/Federation）、Canonical Request Signature 的多层验证——安全纵深设计到位。

3. **Oracle 防线意识强** (05-visibility.md §10): 主动识别跨接口信息泄露路径——`omitted_count` 分桶、拒绝码等价类、dry_run/explain 脱敏、`fog_of_war=true` 禁止 `player_view=full`——体现了良好的安全设计文化。

4. **OS 层加固 Checklist 实现级细节** (04-wasm-sandbox.md §9): seccomp 白名单、cgroup 资源限制、命名空间隔离、CI 验证命令——不仅停留在设计层面，直接给出了可执行的验证清单。

5. **Wasmtime CVE SLA 完善** (CVE-SLA.md): 分级响应时间（24h/72h/1w）、完整的 monitor→assess→patch→test→deploy 流程、回滚策略含复盘要求——生产级别的安全运维规范。

6. **Transport 拆分 + DNS Rebinding 防御** (03-mcp-security.md §2): Browser vs Agent 端点的安全合同明确分离，DNS rebinding 防御矩阵覆盖 6 种攻击向量。

7. **Refresh Token Rotation + Grace Period** (auth.md §14.1): 每次使用后轮换 + 受信/非受信设备差异化 grace period（10s vs 60s）——在安全性和可用性间取得良好平衡。

---

## 4. CrossCheck — 需要跨方向检查

以下是我怀疑但超出安全方向范围的问题，需指定目标方向验证：

- **CX1**: Command Validation Pipeline（`specs/core/02-command-validation.md`）中，每个 command type 是否对 player_id 进行强制绑定（从 auth context 注入而非信任 JSON 中的 player_id）？deferred command model 下 WASM 返回的 CommandIntent JSON 是否可能伪造 player_id？ → **建议 Architect 检查 CommandIntent → Validator 的 trust boundary**

- **CX2**: Tick 调度器中，多个 Sandbox Worker 并行执行 WASM tick() 后，指令收集器如何进行冲突解决（去重、冲突解决、反作弊）？具体算法是什么？若两个玩家在同 tick 对同一资源执行互斥操作（如同时 pickup），冲突解决的确定性是否保证？→ **建议 Architect 检查 Tick 调度器的冲突解决算法**

- **CX3**: `host_path_find` 的 cache key 包含 `player_visibility_fingerprint`。不同玩家的 terrain 可见性不同，path 结果理应不同。但这意味着每个玩家的 path_find cache 是独立的——在高并发下，cache 命中率可能极低（500 玩家 × 不同视野 = 500 份独立缓存）。是否有共享缓存层的设计？→ **建议 Architect 检查 path_find 缓存的性能和命中率预期**

- **CX4**: 联邦身份的 `revocation_fallback` 策略中，`reject_for_code` 模式下 CRL 过期后拒绝 `CodeSigningCertificate` 但仍允许 login。这个 "仍允许 login" 的信任边界是否足够？登录后玩家可执行只读操作——在 competitive 世界中，只读访问是否可能造成不公平优势？→ **建议 Game Designer 评估联邦玩家在 CRL 过期后的只读访问风险**

- **CX5**: `swarm_simulate` 使用 snapshot 副本执行，不修改世界状态。但模拟执行的 WASM 是否可能通过 side channel（如 host function 调用模式、执行时间差异）泄露信息？模拟是否与真实 tick 使用相同的 host function 过滤（`is_visible_to`）？→ **建议 Architect 检查 simulate 环境的隔离性**

---

## 附录: 评审方法论

- **协议一致性验证**: 检查 auth.md 内部 nonce/version_counter 的一致性 → 发现 C1
- **数据流追踪**: Snapshot → WASM → Commands → Validator → ECS — 每一步的 trust boundary 检查 → 发现 CX1, CX2
- **竞态条件检测**: 并行 WASM worker 的 Store reset 安全性 → 发现 H2；Dragonfly 崩溃下的 nonce 重放 → 发现 M1
- **算法边界**: pathfinding 最大计算量 → 发现 M5
- **"信任下游会校验" 假设**: Auth Service 标记删除后信任 Engine 原子处理 → 发现 M4
