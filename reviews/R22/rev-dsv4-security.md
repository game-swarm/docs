# R22 Security Review — DeepSeek V4 Pro

> **Reviewer**: rev-dsv4-security (DeepSeek V4 Pro)
> **Scope**: Phase 1 Clean-Slate — auth, MCP security, visibility, command source, WASM sandbox, persistence, CVE-SLA
> **Documents read**: 9 (README, auth, api-registry, mcp-security, visibility, command-source, CVE-SLA, wasm-sandbox, persistence-contract)
>
> **视角**: 协议一致性验证、数据流追踪、竞态条件检测、信任边界分析

---

## 1. Verdict

**CONDITIONAL_APPROVE**

设计整体安全架构扎实：应用层证书链、用途隔离证书、WASM 沙箱多层隔离、可见性 oracle 闭合、持久化 hash 链均为正确方向。但存在 1 个 Critical（文档级协议矛盾）、3 个 High 级别问题需要修正。所有问题均可在设计阶段解决，不涉及架构推翻。

---

## 2. 发现的问题

### Critical

#### C1: CSR 载荷中 `challenge` 字段传递矛盾 — 可能导致 PoW 绕过

**文件**: `design/auth.md` §5.2 vs §9.3
**严重性**: Critical

**问题描述**:

- §5.2 CSR payload 格式包含 `challenge: <server challenge>` 字段，暗示客户端在 CSR 中回传 challenge 原文
- §9.3 明确声明服务端从 FDB 读取权威 challenge，客户端**不提交** challenge 或 difficulty——`swarm_submit_csr` 的 params 中只有 `challenge_id + nonce + csr_signature`
- 若服务端实现按 §5.2 的 payload 格式验证 CSR 签名（签名覆盖 `challenge` 字段），而 challenge 验证按 §9.3 从 FDB 读取，则可能出现：
  - 签名验证用的 challenge ≠ 服务端 FDB 中的 challenge
  - 攻击者可用旧 challenge 的 CSR 签名重放到新 challenge 上下文

**建议**:
统一 CSR payload 定义：移除 `challenge: <server challenge>` 字段，或明确标注该字段在 CSR canonical payload 中不从客户端接收、由服务端从 FDB 回填后再验签。推荐方案：CSR canonical payload 仅包含 `challenge_id`（作为 challenge 的引用），服务端验签时用 `challenge_id` 从 FDB 取出 challenge 原文，重建签名输入。

**合同要求**: auth.md §5.2 与 §9.3 必须一致化。建议在 §5.2 的 CSR payload 中将 `challenge: <server challenge>` 改为 `challenge_id: <challenge_id>`，并在注释中说明「challenge 原文由服务端从 FDB 读取，不进入 CSR 签名载荷」。

---

### High

#### H1: Worker Pool Store Reset 验证缺失 — 跨 tick 状态泄漏风险

**文件**: `specs/core/04-wasm-sandbox.md` §1
**严重性**: High

**问题描述**:
Sandbox 采用 long-lived worker pool 模型，每 tick 通过 Store reset 清空 WASM 线性内存、重置 fuel counter、重建 Instance。文档描述为"严格 Store reset"，但**未定义 Store reset 的正确性验证机制**：

- 如何保证 Store reset 后线性内存确实全零（无前次 tick 残留）？
- 如何保证 fuel counter 确实重置为 MAX_FUEL（无累积）？
- 若 Wasmtime 内部有未文档化的跨 Instance 状态残留（如编译缓存、JIT 代码段），是否影响确定性？

**攻击场景**: 若 Store reset 存在 bug（如只重置了 WASM 页表但未清零物理页），恶意 WASM 模块可在 tick N 写入数据，tick N+1 读取——跨玩家信息泄漏。

**建议**:
1. 在 CI 中增加 Store reset 验证测试：在 tick N 写入标记值到 WASM 线性内存 → Store reset → tick N+1 断言线性内存全零
2. 添加 `post_reset_fuel_check`：Store reset 后立即读取 `store.get_fuel()` 断言等于 MAX_FUEL
3. 考虑在每次 Store reset 后执行一次「哨兵 tick」——运行一个仅返回空指令且验证自身内存全零的微型 WASM 模块——作为池化 worker 的健康检查

**合同要求**: 在 04-wasm-sandbox.md 的 Store reset 描述中增加验证步骤规范。

---

#### H2: seccomp `write` 允许 vs cgroup `wbps=0` 矛盾 — 输出路径不确定

**文件**: `specs/core/04-wasm-sandbox.md` §4.1 vs §9.1
**严重性**: High

**问题描述**:

- §4.1 seccomp 白名单明确允许 `write` 系统调用（用于输出指令 JSON）
- §9.1 cgroup `io.max` 表显示 `wbps=0`（禁止写）
- 若 sandbox 进程需要 `write` 来输出结果（到 Unix socket 或 stdout），而 cgroup 阻断了所有写 I/O，则进程行为不确定：可能收到 SIGBUS、EPIPE、或静默丢弃输出
- 更严重的是：如果实际部署中 cgroup write 限制未生效（管理员跳过），而 CI 验证依赖 cgroup 限制存在，则形成「测试通过但生产无防护」的 gap

**建议**:
1. 确认 sandbox 输出路径：如果通过 Unix socket fd（在 seccomp 锁定前传入）输出，cgroup `io.max` 的 `wbps=0` 是否影响 Unix socket write？
2. 如果 `wbps=0` 确实阻断输出 → 改为 `wbps=1048576`（允许有限写入）或移除写限制
3. 如果 Unix socket write 不受 cgroup io.max 限制 → 在 §9.1 表中标注「Unix socket 写不受此限制」
4. CI 验证必须模拟生产 cgroup 配置，确保实际 I/O 路径可工作

**合同要求**: 统一 seccomp 白名单和 cgroup 限制，消除矛盾。在 §9.1 表中增加一列「适用 I/O 类型」说明每项限制的作用范围。

---

#### H3: `username_visibility = "public"` 模式泄露用户名存在性

**文件**: `design/auth.md` §7.2
**严重性**: High

**问题描述**:
`username_visibility = "public"` 模式下，`swarm_submit_csr` 在 PoW 验证之前先检查用户名是否存在，若 taken 则直接返回 `username_taken`（不消费 challenge）。这意味着：

- 攻击者无需完成 PoW 即可枚举已注册用户名
- PoW 的设计目的（防批量注册/枚举）被绕过
- 该模式默认值未明确——若默认 `public`，所有部署默认暴露用户名枚举面

**建议**:
1. 将 `username_visibility` 默认值强制为 `"private"`
2. 在 `"public"` 模式的文档中明确标注安全风险：「此模式允许无 PoW 成本的用户名枚举」
3. 考虑完全移除 `"public"` 模式，统一为 `"private"` 行为（先 PoW 后检查）——简化实现，消除配置错误风险

---

### Medium

#### M1: CodeSigningCertificate TTL 过长（180 天）— 吊销窗口过大

**文件**: `design/auth.md` §5.3, §5.4
**严重性**: Medium

CodeSigningCertificate 最长 180 天有效期。在此期间若证书私钥泄露，攻击者可在吊销生效前部署恶意 WASM。虽然证书吊销后可按 revocation reason 冻结/回滚模块，但：

- CRL 缓存延迟最高 60s（auth.md §10.8）
- Federation CRL 同步间隔 60s（auth.md §15.2a）
- 攻击窗口 = 泄露到检测 + CRL 传播延迟

**建议**: 将 CodeSigningCertificate TTL 默认值缩短至 30 天，允许部署者按需调整。常用设备续签成本低（本地私钥证明持有即可），不应以长 TTL 换取便利性。

---

#### M2: Pathfinding 预算 "先到先得" 可被恶意利用

**文件**: `specs/reference/api-registry.md` §5.6
**严重性**: Medium

全局 pathfinding 预算 100,000 explored nodes/tick 按 "先到先得" 分配。若恶意玩家在 COLLECT 阶段早期提交大计算量 pathfinding 请求，可耗尽全局预算，导致其他玩家 pathfinding 失败。

**建议**:
1. 改为预留制：每玩家保底份额 = `floor(100,000 / active_players)`，即使该玩家尚未提交请求也保留
2. 或增加 per-player hard cap（如 max 20,000 nodes/player），超限即 `ERR_PLAYER_BUDGET`
3. pathfinding host function 调用已限制 10/tick，但单次调用的节点数无上限——应增加单次调用 node 上限

---

#### M3: Snapshot `omitted_count` 格式不一致（文档矛盾）

**文件**: `specs/security/03-mcp-security.md` §6.1 vs `specs/security/05-visibility.md` §10.2
**严重性**: Medium

- 03-mcp-security.md §6.1 的 snapshot JSON 示例中 `"omitted_count": 0` 显示为整数
- 05-visibility.md §10.2 将 `omitted_count` 改为分桶字符串值（`"few"`, `"some"`, `"many"`, `"extreme"`）

这是文档内部的修复/未修复不一致——visibility spec 已正确识别 oracle 风险并修复（分桶脱敏），但 mcp-security spec 仍引用旧格式。

**建议**: 更新 03-mcp-security.md §6.1 的 snapshot JSON 示例，将 `omitted_count` 改为分桶字符串格式。

---

#### M4: RuleMod 能力白名单缺乏具体约束

**文件**: `specs/security/09-command-source.md` §2.2, §2.3
**严重性**: Medium

RuleMod source 的 capability whitelist 包括 `damage_entity, set_entity_flag, deduct_resource, award_resource, emit_event`，但**未定义**：

- 每个 capability 的数值上限（damage 最多多少？deduct 最多多少？）
- 是否受 `is_visible_to` 约束（能否 damage 不可见实体？）
- 能否跨玩家操作（deduct_resource 从任意玩家扣除？）

**建议**: 在 09-command-source.md 中为 RuleMod capability 增加 per-action 约束矩阵，明确每项操作的 subject scope、数值上限、可见性要求。

---

### Low

#### L1: `recovery_password` 通过 `swarm_submit_csr` 明文传输

**文件**: `design/auth.md` §10.3
**严重性**: Low

`swarm_submit_csr` 的 params 中包含 `recovery_password` 可选字段，在 HTTP 不安全传输场景下会明文暴露。文档 §5.7 提到「涉及恢复 token、私密邮箱、管理员恢复链接时，payload 应加密给服务器应用层证书 public key」，但未明确 recovery_password 是否在此列。

**建议**: 明确标注 `recovery_password` 在 HTTP 场景必须加密传输（使用 Server Root CA 公钥加密），或要求 recovery_password 仅通过已建立应用层证书安全通道的后续请求设置。

---

#### L2: CVE 监控关键 crate 列表缺少 `wasmtime` 自身以外的 sandbox 依赖

**文件**: `specs/security/CVE-SLA.md`
**严重性**: Low

Critical crate 列表包含 `blake3`, `ed25519-dalek`, `ring`, `rustls`, `tokio`, `serde`, `serde_json`, `wasmparser`, `cranelift-codegen`, `cap-std`, `nix`, `libc`, `crossbeam`, `parking_lot`。但缺少：

- `wasmtime-wasi`（虽禁用但代码仍在依赖树中）
- `cranelift-*` 其他子 crate
- `wiggle`（WASI 宏生成代码）

**建议**: 将 critical 列表扩展为「所有 `wasmtime` 组织下的直接和间接依赖 + 上述手工指定列表」，使用 `cargo audit` 自动覆盖而非手工维护。

---

#### L3: 联邦 CRL 同步首次全量获取缺少超时后的降级策略

**文件**: `design/auth.md` §15.2a
**严重性**: Low

联邦 CRL 首次同步「阻塞至成功或超时（30s）」。超时后行为未定义——是拒绝所有联邦登录（安全优先）还是允许（可用性优先）？

**建议**: 明确首次 CRL 同步超时后的行为，与 `revocation_fallback` 配置联动。

---

#### L4: 账号删除 `asset_disposition = "abandon"` 的无人控制实体可作为匿名攻击向量

**文件**: `design/auth.md` §13.1
**严重性**: Low

当 `asset_disposition = "abandon"` 时，drone/建筑留在世界中无人控制。这些实体可能：
- 阻塞地图位置
- 成为其他玩家的免费资源（recycle）
- 在特定规则下被 AI 玩家利用

**建议**: 为 abandon 模式增加实体衰减计时器（如 100 ticks 后自动 despawn），防止永久僵尸实体。

---

## 3. 亮点

1. **应用层证书链设计优秀**: CSR → 用途隔离证书 → canonical request signature 的信任链完整闭环。证书=认证根、私钥签名=操作授权的模型清晰，避免了 JWT 作为独立信任根的常见反模式。

2. **可见性 oracle 闭合**: `NotVisibleOrNotFound` 合并码、`omitted_count` 分桶脱敏、`player_view=full` 与 `fog_of_war=true` 的组合被 `validate_config` 拒绝——这些都是精心设计的反信息泄露措施。

3. **持久化分层与异步 blob 上传**: FDB commit 先于对象存储写入的设计解耦了事务延迟与 I/O 吞吐。hash 链贯穿存储层保证了完整性可验证，commit retry 不重跑 WASM 避免了双倍扣费。

4. **WASM 沙箱深度防御**: seccomp + cgroup v2 + 网络命名空间 + 只读根文件系统 + fuel metering + epoch interruption 形成五层隔离，远超典型游戏服务器沙箱。

5. **Transport 安全拆分**: Browser vs Agent 的独立安全合同（Origin/CSRF vs 应用层证书签名）避免了「一刀切」认证的常见问题。WebSocket per-message seq + Ed25519 MAC 防会话内重放。

6. **Auth Service 与 Engine 的证书验证分离**: Auth Service 持有 CA 签发能力但 Engine 只消费已验证的 principal——最小权限原则在子系统边界的正确应用。

---

## 4. CrossCheck — 需要跨方向检查

以下问题从安全视角发现，但根因可能在其他方向（架构、游戏设计、接口规范）——建议对应方向审查：

- **CX1**: Worker pool Store reset 的正确性保证需要 Engine 模块验证 → 建议 **Architect** 检查 Engine tick 生命周期中 Store 对象的生命周期管理是否形式化定义
- **CX2**: `username_visibility` 配置项同时影响安全（枚举面）和用户体验（注册流程） → 建议 **Game Designer** 评估注册 UX 在 `private` 模式下的摩擦是否可接受
- **CX3**: Pathfinding 全局预算 "先到先得" 可能退化为非公平分配 → 建议 **Architect** 检查 Engine 资源调度是否需要 per-player reservation 机制
- **CX4**: RuleMod 的 capability whitelist 具体约束（数值上限、可见性要求）涉及游戏平衡 → 建议 **Game Designer** 定义 per-capability 的数值边界
- **CX5**: CodeSigningCertificate 180 天 TTL 的安全/便利权衡 → 建议 **Architect** 评估 30 天 TTL 对 CI/CD 自动化部署 pipeline 的影响
- **CX6**: `omitted_count` 格式不一致（整数 vs 分桶字符串）是 API 合约层面的缺陷 → 建议 **Architect** 以 api-registry.md (IDL 生成) 为权威源统一所有文档

---

## Appendix: 审查方法

- **协议一致性验证**: 交叉比对 auth.md CSR payload 定义与服务端验证流程、mcp-security.md snapshot 格式与 visibility.md 脱敏策略
- **数据流追踪**: CSR 提交 → PoW 验证 → 证书签发 → 请求签名 → Gateway 验签 → Engine Principal 注入 → Command Validation → ECS Apply
- **竞态条件检测**: Worker pool Store reset、FDB commit retry 的 collect_id 复用、refresh token rotation grace period
- **信任边界分析**: Auth Service ↔ Engine ↔ Gateway ↔ Sandbox Worker 之间的 principal 传递不变量
