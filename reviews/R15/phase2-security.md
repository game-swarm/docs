# R15 Phase 2 CrossCheck — Security 补充阅读

Verdict: REQUEST_MAJOR_CHANGES

Scope: 仅补读 `rev-*.md` 中指向 Security 的 CrossCheck，不重跑完整安全评审。重点来源包括 `rev-gpt-apidx.md`、`rev-dsv4-determinism.md`、`rev-gpt-determinism.md`、`rev-dsv4-performance.md`、`rev-gpt-economy.md`、`rev-gpt-designer.md`。

## Critical

无新增 Critical。Phase 2 补读确认多数问题与 R15 Speaker 已归入 B5/B7 的安全授权、sandbox、经济滥用合同缺口同源；本文件不重复升级为 Critical。

## High

### CrossCheck item: rev-gpt-apidx CX4 — MCP 明文/TLS/CA pinning/nonce 签名措辞
Finding: `specs/reference/mcp-tools.md` §认证模型称“HTTP 等不安全传输可以完成身份认证与完整性校验”，`specs/security/03-mcp-security.md` 也写 Agent/CLI 可使用 HTTP + 应用层证书签名；但 `specs/gateway-protocol.md` §8 又写生产环境强制 `wss://`、禁止 `ws://`。这会误导实现者把 TLS 视为可选，尤其是首次 trust-on-first-use pinning 前仍可能被 MITM 替换 Root CA fingerprint。Nonce/Timestamp/Signature 已覆盖请求完整性和重放窗口方向，但文档缺少“首次 pinning 必须通过已认证渠道或 OOB fingerprint 校验”的强约束，也未明确 HTTP-only 仅限 localhost/dev/bootstrap 场景。
disposition: high

### CrossCheck item: rev-gpt-determinism CX3 — `sandbox.relaxed=true` 与 syscall/确定性
Finding: `04-wasm-sandbox.md` 前文明确禁止 `clock_gettime` 和 WASI clocks/random，但 §9.5 对 relaxed 模式写 `clock_gettime` 允许且“风险：无——引擎仍覆盖返回值”。这对安全审计是高风险措辞：seccomp 层一旦允许真实 syscall，除非实现证明所有调用路径都被 WASI/host shim 截获，否则 native/JIT/runtime 路径仍可能获得 wall-clock、形成 timing/covert channel 或跨节点 replay 分叉。生产拒绝 `sandbox.relaxed=true` 是正确的，但 dev/test replay、CI fixture 和 MOD 世界仍可能污染确定性假设。
disposition: high

### CrossCheck item: rev-gpt-economy CX4 / rev-gpt-designer CX5 — alliance/transfer/query 滥用
Finding: `rev-gpt-economy` 已指出 allied direct transfer 可绕过本地/全局转换损耗、转换时间、存储税、新玩家资源门和 No Teleport。补读确认可见性 spec 对普通实体/市场/排行榜较完整，但未给 allied transfer、Contract Board、Market Contracts、same-origin quota、new_player_transfer_lock 的统一执行点和审计归因。该类接口一旦进入 MVP，会形成典型洗钱/刷号/faucet 放大路径：大号-小号联盟拆分资产规避 progressive tax，后方账号即时补给前线，或通过合约押金/奖励结算绕过 transfer lock。
disposition: high

### CrossCheck item: rev-dsv4-performance CX1 / rev-gpt-determinism CX4 — world_seed 生命周期与泄露恢复
Finding: 可见性文档把 `world_seed`/RNG 状态列为 Admin-only，tick spec 使用 `world_seed` 驱动 deterministic replay 和 shuffle，DEFERRED 记录 seed rotation 默认 10,000 tick 且边界 CI 尚待实现。问题不在“是否公开”而在运维合同不足：world_seed 被设计成 TLS 私钥级秘密，但缺少访问矩阵、日志脱敏规则、备份/导出限制、泄露检测指标、泄露后 seed bump/epoch rollover 的 replay 影响说明。若 seed 泄露，攻击者可预测未来 shuffle/RNG；若 rotation 处理不当，又会破坏 replay 或 rollback 确定性。
disposition: high

### CrossCheck item: rev-gpt-apidx CX2 / sandbox host budget — host function budget 与最小请求最大开销
Finding: `04-wasm-sandbox.md` 给出 Host function 1000/tick、`host_path_find` 10/tick + 100,000 explored_nodes，总体方向正确；但 `01-tick-protocol.md` 与 sandbox 文档仍存在输出 JSON “截断/拒绝”语义、cgroup CPU/pids 数值、path_find 100 vs 10 的旧冲突。尤其 `host_get_objects_in_range` 响应 64KB、`host_path_find` 按实际工作量计费，若全局 tick budget/fair share 未成为唯一权威，攻击者仍可用最小 WASM 循环触发大量 host-side A*/visibility/filter 序列化开销。此项与 Speaker B6/B5 同源，应要求机器可读 limits manifest 和 per-player + global admission。
disposition: high

## Medium

### CrossCheck item: rev-dsv4-determinism CX2 — safe_mode rejection vs visibility-first
Finding: `safe_mode` 语义目前只写“其他玩家无法在该房间执行任何敌对操作”，而 `RejectionReason` 列表同时有 `NotVisibleOrNotFound`、`TargetNotVisible` 等可见性优先错误。若对可见 safe_mode 目标返回 `SafeModeActive`，会泄露“目标存在且处于 safe_mode”；若一律返回 `NotVisibleOrNotFound`，玩家调试体验差且难以解释为何视野内目标不可攻击。建议采用两层语义：玩家可见且 safe_mode 状态本身是公开房间规则时返回安全的 `ProtectedBySafeMode`；不可见/不存在仍统一 `NotVisibleOrNotFound`。同时禁止通过不同 fuel refund、cooldown、trace detail、latency 形成 side channel。
disposition: medium

### CrossCheck item: rev-gpt-determinism CX2 — `swarm_get_random(sequence)` / host RNG API covert channel
Finding: 当前 sandbox 文档禁止 WASI random，并提到“用 host function 提供的种子 PRNG”，但允许 host function 列表未包含 `swarm_get_random`。如果未来暴露 deterministic RNG host API，不能返回或可推导 `world_seed`，也不能让调用者通过 sequence 空间影响其他玩家/全局 RNG stream。安全可接受路径是 per-player/per-tick/domain-separated stream，例如 `Blake3("player-rng" || seed_epoch_public_id || player_id || tick || sequence)`，只返回 bounded bytes，计入 host-call budget，并在 TickTrace 记录调用摘要；否则应保持 close，不暴露该 API。
disposition: medium

### CrossCheck item: rev-gpt-economy CX5 — `swarm_get_economy` / 经济仪表盘可见性
Finding: 经济反馈循环是必要 UX，但全局/本地存储、税率、趋势、预测若未按 `is_visible_to` 和数据分级过滤，会泄露敌方仓储、PvE farm 路径、联盟资产与战略压力。当前 visibility spec 明确隐藏其他玩家资源总量，排行榜仅公开 GCL/房间数/drone 数；因此 `swarm_get_economy` 应默认仅返回 Self 数据、公开聚合数据需 k-anonymity/延迟/降精度，联盟级数据需显式同盟授权和审计。
disposition: medium

### CrossCheck item: rev-gpt-designer CX2/CX4 — replay/spectate/privacy
Finding: `05-visibility.md` 对 spectator/replay 已有较好分层：World 默认不公开他人回放，public spectate 需 delay，private replay 过滤资源、env、debug、commands。但 `player_view="full"` 允许玩家屏幕/MCP 全地图、`public_spectate=true` 可全地图实体推送，仍需要 world.toml 安全默认和 admin/mod 审批边界，避免 World 为传播目标打开实时情报泄露。
disposition: medium

## Informational

### CrossCheck item: rev-gpt-apidx CX3 — visibility-first 与调试体验
Finding: Opaque error 的安全直觉正确。补充建议是把玩家可见 hint 放到自身 trace 中，而不是扩大 API 错误码：例如 `NotVisibleOrNotFound` + `hint_class: check_visibility_or_id`，只对调用者自身显示，不进入公开日志或他人 replay。
disposition: close

### CrossCheck item: rev-gpt-apidx CX5 — Rhai 服主信任层
Finding: 本轮输入仅要求 Security 复核，Rhai 更偏 Architect/Security 共同权威边界。安全倾向是 Rhai 只操作声明式 rules/custom action DTO，不暴露 ECS mutable internals；若后续进入实现，需独立审计 MOD sandbox 与 deterministic manifest。
disposition: medium

## Required follow-up wording changes

1. 将 “HTTP 等不安全传输可以完成身份认证与完整性校验” 改为 “生产公网必须使用 TLS/WSS；应用层签名是额外认证与完整性层，不替代 TLS。HTTP 仅限 localhost/dev 或经 OOB fingerprint pinning 的受控 bootstrap。”
2. 将 `sandbox.relaxed` 的 `clock_gettime` 风险从“无”改为“高风险，仅 development；必须由 CI 证明所有时间来源被 deterministic shim 覆盖，且 relaxed 世界不得参与 ranked/replay-verifier 兼容承诺。”
3. 为 `safe_mode` 增加 rejection decision table：不可见/不存在、可见且公开 safe_mode、可见但保护状态不应公开三种路径。
4. 为 seed 管理补充密钥生命周期：access roles、log redaction、backup policy、leak detection、rotation/epoch rollback runbook、replay compatibility。
5. 为 economy/alliance/contract/transfer/query 增加 abuse matrix：same-origin account group、new player lock、tax attribution、distance/locality、cooldown/capacity、audit ledger、visibility filtering。
